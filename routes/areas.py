"""
Rutas de Áreas - Cálculo de clasificación de clientes por nivel/color
Realiza spatial join entre puntos GPS de clientes y polígonos de avisos
Guarda clasificación en BD (tabla clientes_por_aviso) y estadísticas por nivel
"""
import io
import logging
from pathlib import Path
import psycopg2

import geopandas as gpd
import pandas as pd
from flask import Blueprint, jsonify, send_file
from CONFIG.db import get_connection, obtener_clientes_por_nivel_desde_bd

BASE_DIR = Path(__file__).parent.parent
TEMP_DIR = BASE_DIR / 'TEMP'

logger = logging.getLogger(__name__)
areas_bp = Blueprint('areas', __name__)


def calcular_area_riesgo_alto(shp_path):
    """Calcula el área total de riesgo alto (ROJO Nivel 4 + NARANJA Nivel 3)"""
    if not Path(shp_path).exists():
        logger.warning("SHP no encontrado: %s", shp_path)
        return 0.0
    
    try:
        gdf = gpd.read_file(shp_path)
        columna_color = None
        for col in ['nivel', 'color', 'NIVEL', 'COLOR', 'Nivel', 'Color']:
            if col in gdf.columns:
                columna_color = col
                break
        
        if not columna_color:
            logger.warning("No se encontró columna de nivel/color en %s", shp_path)
            return 0.0
        
        # Filtrar solo Nivel 3 (Naranja) y Nivel 4 (Rojo) - riesgo ALTO
        mask = gdf[columna_color].isin(['Nivel 3', 'Nivel 4', 3, 4, 'Naranja', 'Rojo', 'naranja', 'rojo'])
        gdf_alto = gdf[mask]
        
        if gdf_alto.empty:
            return 0.0
        
        gdf_alto = gdf_alto.to_crs(epsg=32718)
        area_total = gdf_alto['geometry'].area.sum() / 1_000_000
        return area_total
    except (IOError, ValueError) as e:
        logger.error("Error calculando área en %s: %s", shp_path, e)
        return 0.0


def encontrar_dia_critico(numero):
    """Encuentra el día con mayor área de riesgo alto"""
    areas = {}
    for dia in [1, 2, 3]:
        shp_path = TEMP_DIR / f'aviso_{numero}' / f'dia{dia}' / 'view_aviso.shp'
        if shp_path.exists():
            area = calcular_area_riesgo_alto(str(shp_path))
            areas[dia] = area
            logger.info("Aviso %d, día %d: %.2f km² de riesgo alto", numero, dia, area)
    
    if not areas:
        logger.warning("No hay días con datos para aviso %d", numero)
        return None, 0.0
    
    dia_critico = max(areas, key=areas.get)
    logger.info("Día crítico para aviso %d: día %d (%.2f km²)", numero, dia_critico, areas[dia_critico])
    return dia_critico, areas[dia_critico]


@areas_bp.route('/api/avisos/<int:numero>/dia-critico', methods=['GET'])
def obtener_dia_critico(numero):
    """Retorna el día con mayor área de riesgo alto"""
    try:
        dia_critico, area = encontrar_dia_critico(numero)
        if dia_critico is None:
            return jsonify({'success': False, 'error': f'No hay datos para aviso {numero}'}), 404
        
        return jsonify({
            'success': True,
            'numero': numero,
            'dia_critico': dia_critico,
            'area_riesgo_alto_km2': round(area, 2),
            'mensaje': f'Use día {dia_critico} para calcular áreas'
        }), 200
    except (IOError, ValueError) as e:
        logger.error("Error obteniendo día crítico: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@areas_bp.route('/api/avisos/<int:numero>/calcular-areas/<int:dia>', methods=['POST'])
def calcular_areas_por_nivel(numero, dia):
    """Calcula y guarda la clasificación de clientes por nivel/color usando spatial join"""
    try:
        logger.info("Iniciando cálculo de áreas para aviso %d, día %d", numero, dia)

        if dia not in [1, 2, 3]:
            return jsonify({'success': False, 'error': 'Día debe ser 1, 2 o 3'}), 400

        shp_path = TEMP_DIR / f'aviso_{numero}' / f'dia{dia}' / 'view_aviso.shp'
        if not shp_path.exists():
            logger.error("SHP no encontrado: %s", shp_path)
            return jsonify({'success': False,
                            'error': f'Shapefile no encontrado en TEMP/aviso_{numero}/dia{dia}/'}), 404

        insertados = guardar_clientes_en_bd(numero, dia, shp_path)
        if insertados is None:
            return jsonify({'success': False,
                            'error': 'Error en spatial join o guardado en BD'}), 500

        # Resumen desde BD
        df = obtener_clientes_por_nivel_desde_bd(numero_aviso=numero)
        resumen = {
            'dia': dia,
            'total_clientes': insertados,
            'clasificacion_por_nivel': df['nivel'].value_counts().to_dict() if df is not None else {},
            'hectareas_por_nivel': (
                df.groupby('nivel')['hectareas'].sum().to_dict()
                if df is not None and 'hectareas' in df.columns else {}
            ),
        }

        logger.info("Resumen generado")
        return jsonify({'success': True,
                        'mensaje': f'Áreas calculadas para aviso {numero}, día {dia}',
                        'resumen': resumen}), 200
    except (IOError, ValueError, RuntimeError) as e:
        logger.error("Error: %s", str(e), exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@areas_bp.route('/api/avisos/<int:numero>/clientes-nivel/<int:dia>', methods=['GET'])
def api_clientes_por_nivel(numero, dia):
    """Retorna clientes clasificados por nivel desde BD"""
    try:
        df = obtener_clientes_por_nivel_desde_bd(numero_aviso=numero)
        if df is None or df.empty:
            return jsonify({'success': False,
                            'error': 'No hay datos para este aviso en BD'}), 404
        clientes = df.to_dict('records')
        return jsonify({'success': True, 'total': len(clientes),
                        'dia': dia, 'clientes': clientes}), 200
    except (IOError, ValueError) as e:
        logger.error("Error: %s", str(e))
        return jsonify({'success': False, 'error': str(e)}), 500


@areas_bp.route('/api/avisos/<int:numero>/resumen-areas/<int:dia>', methods=['GET'])
def resumen_areas(numero, dia):
    """Retorna resumen estadístico de clasificación desde BD"""
    try:
        df = obtener_clientes_por_nivel_desde_bd(numero_aviso=numero)
        if df is None or df.empty:
            return jsonify({'success': False,
                            'error': 'No hay datos para este aviso en BD'}), 404

        resumen = {
            'dia': dia,
            'total_clientes': len(df),
            'total_hectareas': float(df['hectareas'].sum()) if 'hectareas' in df.columns else 0,
            'por_nivel': {}
        }
        if 'nivel' in df.columns:
            for nivel in df['nivel'].unique():
                if pd.notna(nivel):
                    subset = df[df['nivel'] == nivel]
                    resumen['por_nivel'][str(nivel)] = {
                        'clientes': len(subset),
                        'hectareas': float(subset['hectareas'].sum()) if 'hectareas' in df.columns else 0,
                        'porcentaje': round(100 * len(subset) / len(df), 2)
                    }
        return jsonify({'success': True, 'resumen': resumen}), 200
    except (IOError, ValueError) as e:
        logger.error("Error: %s", str(e))
        return jsonify({'success': False, 'error': str(e)}), 500


@areas_bp.route('/api/avisos/<int:numero>/descargar-clientes-csv/<int:dia>', methods=['GET'])
def descargar_csv(numero, dia):
    """Descarga CSV con clasificación de clientes generado desde BD"""
    try:
        df = obtener_clientes_por_nivel_desde_bd(numero_aviso=numero)
        if df is None or df.empty:
            return jsonify({'error': 'No hay datos para este aviso en BD'}), 404

        buffer = io.StringIO()
        df.to_csv(buffer, index=False, encoding='utf-8')
        buffer.seek(0)
        return send_file(
            io.BytesIO(buffer.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'clientes_por_nivel_aviso_{numero}_dia{dia}.csv'
        )
    except (IOError, ValueError) as e:
        logger.error("Error descargando CSV: %s", str(e))
        return jsonify({'error': str(e)}), 500


# ============= HELPER FUNCTION (NO FLASK) =============
def obtener_clientes_por_nivel(numero, dia, shp_path=None):
    """
    Obtiene clasificación de clientes por nivel/color (retorna DataFrame, no guarda CSV).
    Versión sin I/O para usarse en pipeline de mapas.
    
    Args:
        numero: ID del aviso
        dia: Día (1, 2, 3)
        shp_path: Ruta al shapefile
    
    Returns:
        pd.DataFrame con columnas: id, nombre_cliente, latitud, longitud, hectareas, nivel
        o None si error
    """
    try:
        if shp_path is None:
            shp_path = TEMP_DIR / f'aviso_{numero}' / f'dia{dia}' / 'view_aviso.shp'
        else:
            shp_path = Path(shp_path)
        
        if not shp_path.exists():
            logger.error(f"SHP no encontrado: {shp_path}")
            return None
        
        # Leer SHP
        shp_alerta = gpd.read_file(str(shp_path))
        
        # Encontrar columna de nivel
        columna_color = None
        for col in ['nivel', 'color', 'NIVEL', 'COLOR', 'Nivel', 'Color']:
            if col in shp_alerta.columns:
                columna_color = col
                break
        
        if not columna_color:
            logger.error(f"No se encontró columna de nivel. Disponibles: {list(shp_alerta.columns)}")
            return None
        
        # Obtener clientes de BD
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, CONCAT(nombre, ' ', apellido) as nombre_cliente, latitud, longitud, hectareas
                FROM clientes 
                WHERE latitud IS NOT NULL AND longitud IS NOT NULL
                ORDER BY id
            """)
            clientes_data = cursor.fetchall()
            cursor.close()
            conn.close()
        except psycopg2.Error as e:
            logger.error(f"Error consultando BD: {e}")
            return None
        
        if not clientes_data:
            logger.warning("No hay clientes con coordenadas")
            return None
        
        # Crear GeoDataFrame
        clientes_df = pd.DataFrame(clientes_data, columns=['id', 'nombre_cliente', 'latitud', 'longitud', 'hectareas'])
        clientes_geo = gpd.GeoDataFrame(
            clientes_df,
            geometry=gpd.points_from_xy(clientes_df['longitud'], clientes_df['latitud']),
            crs="EPSG:4326"
        )
        
        # Igualar CRS
        if clientes_geo.crs != shp_alerta.crs:
            clientes_geo = clientes_geo.to_crs(shp_alerta.crs)
        
        # Spatial join
        resultado = gpd.sjoin(
            clientes_geo,
            shp_alerta[[columna_color, 'geometry']],
            how='left',
            predicate='within'
        )
        
        resultado_df = resultado.drop(columns=['geometry', 'index_right']).copy()
        resultado_df = resultado_df.rename(columns={columna_color: 'nivel'})
        
        # Mapear niveles
        mapeo_nivel_color = {
            'Nivel 4': 'Rojo', 'Nivel 3': 'Naranja', 'Nivel 2': 'Amarillo', 'Nivel 1': 'Verde',
            4: 'Rojo', 3: 'Naranja', 2: 'Amarillo', 1: 'Verde',
            'Rojo': 'Rojo', 'Naranja': 'Naranja', 'Amarillo': 'Amarillo', 'Verde': 'Verde'
        }
        resultado_df['nivel'] = resultado_df['nivel'].map(mapeo_nivel_color).fillna('Verde')
        
        logger.info(f"✓ Clientes procesados para aviso {numero}: {len(resultado_df)} registros")
        return resultado_df
        
    except Exception as e:
        logger.error(f"Error en obtener_clientes_por_nivel: {e}")
        return None


def guardar_clientes_en_bd(numero, dia, shp_path=None):
    """
    Guarda clasificación de clientes en BD (tabla clientes_por_aviso).
    Reemplaza generar_csv_clientes_por_nivel. Llamada desde procesar_aviso.py.

    Args:
        numero: ID del aviso
        dia: Día (1, 2, 3)
        shp_path: Ruta al shapefile (si no está en TEMP/aviso_{numero}/dia{dia}/view_aviso.shp)

    Returns:
        Cantidad de registros guardados o None si error
    """
    try:
        resultado_df = obtener_clientes_por_nivel(numero, dia, shp_path)
        if resultado_df is None:
            return None

        conn_bd = get_connection()
        cursor_bd = conn_bd.cursor()
        insertados = 0
        for _, fila in resultado_df.iterrows():
            cursor_bd.execute(
                """INSERT INTO clientes_por_aviso (cliente_id, numero_aviso, nivel)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (cliente_id, numero_aviso)
                   DO UPDATE SET nivel = EXCLUDED.nivel""",
                (int(fila['id']), numero, fila['nivel'])
            )
            insertados += 1
        conn_bd.commit()
        cursor_bd.close()
        conn_bd.close()

        logger.info(f"✓ BD actualizada: {insertados} registros para aviso {numero} día {dia}")
        return insertados

    except Exception as e:
        logger.error(f"Error en guardar_clientes_en_bd: {e}")
        return None


# Alias de compatibilidad para código que llame la versión anterior
generar_csv_clientes_por_nivel = guardar_clientes_en_bd
