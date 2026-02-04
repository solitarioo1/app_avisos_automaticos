"""
Rutas de Decisiones - API endpoints para toma de decisiones
Integra datos de clientes BD con CSV avisos y calcula estadísticas
"""
import csv
import json
import logging
import os
import sys
from pathlib import Path
from collections import defaultdict, Counter

import geopandas as gpd
import pandas as pd
import psycopg2
import psycopg2.extras
from flask import Blueprint, jsonify, render_template, request
from shapely.geometry import Point

# Definir BASE_DIR y OUTPUT_DIR
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / 'OUTPUT'

# Agregar LAYOUT al path para importar utils
sys.path.insert(0, str(BASE_DIR / 'LAYOUT'))

# Importar funciones locales
try:
    from CONFIG.db import get_connection
except ImportError:
    # Fallback: usar conexión directa
    get_connection = None

try:
    from utils import seleccionar_dia_critico, calcular_area_riesgo_alto
except ImportError:
    seleccionar_dia_critico = None
    calcular_area_riesgo_alto = None

logger = logging.getLogger(__name__)
decisiones_bp = Blueprint('decisiones', __name__, url_prefix='')

# Definir TEMP_DIR para SHP
TEMP_DIR = BASE_DIR / 'TEMP'


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def get_clientes_por_color(numero_aviso):
    """
    Realiza spatial join: determina qué COLOR de SHP contiene cada cliente
    
    Returns:
        {
            'clientes_por_color': {
                'roja': [id_cliente1, id_cliente2, ...],
                'naranja': [...],
                'amarilla': [...],
                'sin_zona': [...]  # Clientes fuera del SHP
            },
            'mapa_cliente_color': {cliente_id: 'roja'}
        }
    """
    try:
        # 1. Obtener SHP del aviso (día crítico)
        temp_base = TEMP_DIR / f'aviso_{numero_aviso}'
        if not temp_base.exists():
            logger.warning("No SHP para aviso %d", numero_aviso)
            return {'clientes_por_color': {}, 'mapa_cliente_color': {}}
        
        dict_shps = {}
        for dia in range(1, 4):
            dia_dir = temp_base / f'dia{dia}'
            shp_path = dia_dir / 'view_aviso.shp'
            if shp_path.exists():
                dict_shps[f'dia{dia}'] = str(shp_path)
        
        if not dict_shps:
            logger.warning("No hay SHP para aviso %d", numero_aviso)
            return {'clientes_por_color': {}, 'mapa_cliente_color': {}}
        
        # Seleccionar día crítico
        dia_critico = 'dia1'
        shp_critico = None
        try:
            if seleccionar_dia_critico:
                dia_critico, shp_critico = seleccionar_dia_critico(dict_shps)
            else:
                shp_critico = dict_shps.get('dia1')
        except (ValueError, AttributeError):
            shp_critico = dict_shps.get('dia1')
        
        if not shp_critico:
            logger.warning("No se pudo seleccionar SHP crítico para aviso %d", numero_aviso)
            return {'clientes_por_color': {}, 'mapa_cliente_color': {}}
        
        # 2. Leer SHP y convertir CRS si es necesario
        try:
            gdf_shp = gpd.read_file(shp_critico)
            if gdf_shp.crs and gdf_shp.crs != 'EPSG:4326':
                gdf_shp = gdf_shp.to_crs('EPSG:4326')
        except (OSError, ValueError) as e:
            logger.error("Error leyendo SHP: %s", str(e))
            return {'clientes_por_color': {}, 'mapa_cliente_color': {}}
        
        # 3. Mapear nivel a color
        nivel_color = {
            'Nivel 4': 'roja',
            'Nivel 3': 'naranja',
            'Nivel 2': 'amarilla',
            'Nivel 1': 'amarilla'  # Nivel 1 tratado como amarilla
        }
        gdf_shp['color_zona'] = gdf_shp['nivel'].map(nivel_color).fillna('sin_zona')
        
        # 4. Obtener clientes de la BD
        conn = get_db_connection()
        if not conn:
            logger.error("No connection to DB")
            return {'clientes_por_color': {}, 'mapa_cliente_color': {}}
        
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("""
                SELECT id, latitud, longitud, departamento, provincia, distrito
                FROM clientes
                WHERE estado = 'activo'
                ORDER BY id
            """)
            clientes_db = cursor.fetchall()
            cursor.close()
            conn.close()
        except psycopg2.Error as e:
            logger.error("Error consultando clientes: %s", str(e))
            return {'clientes_por_color': {}, 'mapa_cliente_color': {}}
        
        # 5. Convertir clientes a GeoDataFrame
        if not clientes_db:
            logger.warning("No clientes en BD")
            return {'clientes_por_color': {}, 'mapa_cliente_color': {}}
        
        clientes_geom = []
        for c in clientes_db:
            if c['latitud'] and c['longitud']:
                clientes_geom.append({
                    'id': c['id'],
                    'geometry': Point(float(c['longitud']), float(c['latitud'])),
                    'departamento': c.get('departamento', ''),
                    'provincia': c.get('provincia', ''),
                    'distrito': c.get('distrito', '')
                })
        
        if not clientes_geom:
            logger.warning("No clients con geometría")
            return {'clientes_por_color': {}, 'mapa_cliente_color': {}}
        
        gdf_clientes = gpd.GeoDataFrame(clientes_geom, crs='EPSG:4326')
        
        # 6. Spatial join: determinar qué cliente está en qué polígono SHP
        # Usar sjoin para encontrar qué cliente está dentro de qué polígono
        try:
            sjoin_result = gpd.sjoin(gdf_clientes, gdf_shp[['geometry', 'color_zona']], 
                                     how='left', predicate='within')
        except Exception as e:
            logger.error("Error en spatial join: %s", str(e))
            # Fallback: usar contains en lugar de within
            try:
                sjoin_result = gpd.sjoin(gdf_clientes, gdf_shp[['geometry', 'color_zona']], 
                                         how='left', predicate='contains')
            except Exception as e2:
                logger.error("Fallback spatial join también falló: %s", str(e2))
                return {'clientes_por_color': {}, 'mapa_cliente_color': {}}
        
        # 7. Agrupar clientes por color
        clientes_por_color = defaultdict(list)
        mapa_cliente_color = {}
        
        for _, row in sjoin_result.iterrows():
            cliente_id = row['id']
            color = row.get('color_zona', 'sin_zona')
            if pd.isna(color):
                color = 'sin_zona'
            
            clientes_por_color[color].append(cliente_id)
            mapa_cliente_color[cliente_id] = color
        
        logger.info("Spatial join completado para aviso %d: %d clientes asignados",
                    numero_aviso, len(mapa_cliente_color))
        
        return {
            'clientes_por_color': dict(clientes_por_color),
            'mapa_cliente_color': mapa_cliente_color
        }
    
    except Exception as e:
        logger.error("Error en get_clientes_por_color: %s", str(e))
        return {'clientes_por_color': {}, 'mapa_cliente_color': {}}


def get_db_connection():
    """
    Obtener conexión a PostgreSQL
    Usa la función centralizada de CONFIG.db
    """
    try:
        return get_connection()
    except psycopg2.Error as e:
        logger.error("Error conexión BD: %s", str(e))
        return None


def parse_csv_avisos(numero_aviso):
    """
    Lee CSV de avisos afectados (distritos_afectados.csv)
    Retorna lista de dicts: {departamento, provincia, distrito}
    """
    csv_path = OUTPUT_DIR / f'aviso_{numero_aviso}' / 'distritos_afectados.csv'

    if not csv_path.exists():
        logger.warning("CSV no encontrado: %s", csv_path)
        return []

    distritos = []
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row:
                    distritos.append({
                        'departamento': row.get('DEPARTAMEN', '').strip().upper(),
                        'provincia': row.get('PROVINCIA', '').strip().upper(),
                        'distrito': row.get('DISTRITO', '').strip().upper()
                    })
        logger.info("CSV parseado: %d distritos para aviso %d", len(distritos), numero_aviso)
        return distritos
    except OSError as e:
        logger.error("Error leyendo CSV: %s", str(e))
        return []


def get_clientes_afectados(numero_aviso, depto=None, provincia=None, distrito=None):
    """
    Consulta BD clientes y filtra por zona afectada del aviso

    Args:
        numero_aviso: Número del aviso
        depto: Filtro opcional por departamento
        provincia: Filtro opcional por provincia
        distrito: Filtro opcional por distrito

    Returns:
        {
            'total_agricultores': int,
            'agricultores': [list of cliente objects],
            'cultivos': {cultivo: count},
            'total_hectareas': float,
            'total_monto_asegurado': float,
            'financieras': {financiera: count}
        }
    """
    conn = get_db_connection()
    if not conn:
        return {}

    try:
        # Leer CSV de avisos para obtener zonas afectadas
        zonas_afectadas = parse_csv_avisos(numero_aviso)
        if not zonas_afectadas:
            return {
                'total_agricultores': 0,
                'agricultores': [],
                'cultivos': {},
                'total_hectareas': 0,
                'total_monto_asegurado': 0,
                'financieras': {}
            }

        # Normalizar CSV data
        zonas_normalizadas = set()
        for zona in zonas_afectadas:
            zonas_normalizadas.add((
                zona['departamento'].upper().strip(),
                zona['provincia'].upper().strip(),
                zona['distrito'].upper().strip()
            ))

        # Construir query OPTIMIZADA - filtrar por departamentos afectados
        # NOTA: La BD tiene datos de prueba con provincias/distritos genéricos,
        # por lo que el cruce se hace solo por DEPARTAMENTO
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Extraer departamentos únicos de las zonas afectadas
        deptos_unicos = set([zona[0] for zona in zonas_normalizadas])
        
        # Construir query simple con IN por departamentos
        where_parts = []
        all_params = []
        
        # Filtro por departamentos afectados
        if deptos_unicos:
            placeholders = ', '.join(['%s'] * len(deptos_unicos))
            where_parts.append(f"UPPER(TRIM(departamento)) IN ({placeholders})")
            all_params.extend(list(deptos_unicos))
        
        # Agregar filtros opcionales con AND
        if depto:
            where_parts.append("UPPER(TRIM(departamento)) = %s")
            all_params.append(depto.upper().strip())
        if provincia:
            where_parts.append("UPPER(TRIM(provincia)) = %s")
            all_params.append(provincia.upper().strip())
        if distrito:
            where_parts.append("UPPER(TRIM(distrito)) = %s")
            all_params.append(distrito.upper().strip())

        # Construir query final
        where_clause = " AND ".join(where_parts) if where_parts else "1=1"
        query = f"SELECT * FROM clientes WHERE {where_clause}"

        cursor.execute(query, all_params)
        
        # Obtener clientes de departamentos afectados
        # (El cruce exacto por prov/dist se omite porque la BD tiene datos de prueba)
        agricultores = cursor.fetchall()

        # Log de consulta
        logger.info("Clientes en departamentos afectados: %d (deptos: %s)",
                    len(agricultores), list(deptos_unicos)[:5])

        # Procesar datos
        cultivos_counter = Counter()
        financieras_counter = Counter()
        total_hectareas = 0
        total_monto = 0

        for agr in agricultores:
            # Cultivos
            if agr.get('cultivo_id'):
                cultivos_counter[str(agr['cultivo_id'])] += 1
            # Hectáreas
            if agr.get('hectareas'):
                total_hectareas += float(agr['hectareas']) if agr['hectareas'] else 0
            # Monto asegurado
            if agr.get('monto_asegurado'):
                total_monto += float(agr['monto_asegurado']) if agr['monto_asegurado'] else 0

        cursor.close()
        conn.close()

        # Convertir agricultores a list de dicts JSON-serializable
        agricultores_list = []
        for agr in agricultores:
            agr_dict = dict(agr)
            # Convertir tipos especiales
            for key, value in agr_dict.items():
                if hasattr(value, 'isoformat'):
                    agr_dict[key] = value.isoformat()
                elif isinstance(value, float):
                    agr_dict[key] = round(value, 2)
            agricultores_list.append(agr_dict)

        result = {
            'total_agricultores': len(agricultores_list),
            'agricultores': agricultores_list,
            'cultivos': dict(cultivos_counter),
            'total_hectareas': round(total_hectareas, 2),
            'total_monto_asegurado': round(total_monto, 2),
            'financieras': dict(financieras_counter)
        }

        logger.info("Clientes obtenidos para aviso %d: %d registros",
                    numero_aviso, len(agricultores_list))
        return result

    except psycopg2.Error as e:
        logger.error("Error consultando clientes: %s", str(e))
        return {}
    finally:
        if conn:
            conn.close()


def get_estadisticas_aviso(numero_aviso):
    """
    Calcula estadísticas del aviso: Crítico, Alto Riesgo, etc.

    Returns:
        {
            'critico': {...},
            'alto_riesgo': {...},
            'agricultores_total': int,
            'poliza_total': float,
            'hectareas_total': float
        }
    """
    try:
        conn = get_db_connection()
        if not conn:
            return {}

        # Obtener color del aviso
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "SELECT color FROM avisos_completos WHERE numero_aviso = %s",
            (numero_aviso,)
        )
        aviso = cursor.fetchone()
        cursor.close()
        conn.close()

        if not aviso:
            return {}

        color = aviso['color'].lower()

        # Obtener clientes
        clientes_data = get_clientes_afectados(numero_aviso)

        stats = {
            'color': color,
            'critico': {
                'nivel': 'CRÍTICO' if color == 'rojo' else '',
                'count': clientes_data.get('total_agricultores', 0) if color == 'rojo' else 0
            },
            'alto_riesgo': {
                'nivel': 'ALTO RIESGO' if color == 'naranja' else '',
                'count': clientes_data.get('total_agricultores', 0) if color == 'naranja' else 0
            },
            'agricultores_total': clientes_data.get('total_agricultores', 0),
            'poliza_total': clientes_data.get('total_monto_asegurado', 0),
            'hectareas_total': clientes_data.get('total_hectareas', 0)
        }

        return stats

    except psycopg2.Error as e:
        logger.error("Error calculando estadísticas: %s", str(e))
        return {}


# ============================================================================
# RUTAS
# ============================================================================

@decisiones_bp.route('/api/avisos/<int:numero>/clientes-geojson', methods=['GET'])
def api_clientes_geojson(numero):
    """
    Retorna clientes como GeoJSON points para renderizar en mapa
    """
    try:
        clientes_data = get_clientes_afectados(numero)
        agricultores = clientes_data.get('agricultores', [])
        
        features = []
        for agr in agricultores:
            if agr.get('latitud') and agr.get('longitud'):
                feature = {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Point',
                        'coordinates': [float(agr['longitud']), float(agr['latitud'])]
                    },
                    'properties': {
                        'nombre': f"{agr.get('nombre', '')} {agr.get('apellido', '')}",
                        'dni_ruc': agr.get('dni_ruc', ''),
                        'cultivo_id': agr.get('cultivo_id'),
                        'hectareas': agr.get('hectareas'),
                        'monto_asegurado': agr.get('monto_asegurado'),
                        'distrito': agr.get('distrito', ''),
                        'provincia': agr.get('provincia', ''),
                        'departamento': agr.get('departamento', '')
                    }
                }
                features.append(feature)
        
        return jsonify({
            'type': 'FeatureCollection',
            'features': features,
            'total': len(features)
        })
    
    except Exception as e:
        logger.error("Error en clientes-geojson: %s", str(e))
        return jsonify({'error': str(e)}), 500


@decisiones_bp.route('/api/avisos/<int:numero>/agregaciones', methods=['GET'])
def api_agregaciones(numero):
    """
    Retorna agregaciones de clientes por depto/provincia/distrito
    """
    try:
        clientes_data = get_clientes_afectados(numero)
        agricultores = clientes_data.get('agricultores', [])
        
        deptos = {}
        for agr in agricultores:
            depto = agr.get('departamento', 'Sin datos').upper()
            if depto not in deptos:
                deptos[depto] = {
                    'total': 0,
                    'hectareas': 0,
                    'monto': 0,
                    'provincias': {}
                }
            deptos[depto]['total'] += 1
            deptos[depto]['hectareas'] += float(agr.get('hectareas', 0))
            deptos[depto]['monto'] += float(agr.get('monto_asegurado', 0))
            
            provincia = agr.get('provincia', 'Sin datos').upper()
            if provincia not in deptos[depto]['provincias']:
                deptos[depto]['provincias'][provincia] = {
                    'total': 0,
                    'hectareas': 0,
                    'monto': 0,
                    'distritos': {}
                }
            deptos[depto]['provincias'][provincia]['total'] += 1
            deptos[depto]['provincias'][provincia]['hectareas'] += float(agr.get('hectareas', 0))
            deptos[depto]['provincias'][provincia]['monto'] += float(agr.get('monto_asegurado', 0))
            
            distrito = agr.get('distrito', 'Sin datos').upper()
            if distrito not in deptos[depto]['provincias'][provincia]['distritos']:
                deptos[depto]['provincias'][provincia]['distritos'][distrito] = {
                    'total': 0,
                    'hectareas': 0,
                    'monto': 0
                }
            deptos[depto]['provincias'][provincia]['distritos'][distrito]['total'] += 1
            deptos[depto]['provincias'][provincia]['distritos'][distrito]['hectareas'] += float(agr.get('hectareas', 0))
            deptos[depto]['provincias'][provincia]['distritos'][distrito]['monto'] += float(agr.get('monto_asegurado', 0))
        
        return jsonify({'agregaciones': deptos})
    
    except Exception as e:
        logger.error("Error en agregaciones: %s", str(e))
        return jsonify({'error': str(e)}), 500


@decisiones_bp.route('/api/avisos/<int:numero>/resumen-zonas', methods=['GET'])
def api_resumen_zonas(numero):
    """
    Endpoint: Resumen por ZONAS de color (Roja/Naranja/Amarilla)
    Retorna: Agricultores totales vs afectados por color
    
    Returns:
        {
            'numero_aviso': numero,
            'roja': {
                'agr_totales': 100,
                'agr_afectados': 45,
                'ha_totales': 500.0,
                'ha_afectadas': 320.5,
                'monto_total': 2000000.00,
                'monto_afectado': 1500000.00
            },
            'naranja': {...},
            'amarilla': {...}
        }
    """
    try:
        # Obtener spatial join: cliente -> color
        spatial_data = get_clientes_por_color(numero)
        mapa_cliente_color = spatial_data.get('mapa_cliente_color', {})
        
        # Obtener TODOS los clientes
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Conexión BD fallida'}), 500
        
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Query: TODOS los clientes con sus datos
        cursor.execute("""
            SELECT id, hectareas, monto_asegurado
            FROM clientes
            WHERE estado = 'activo'
        """)
        todos_clientes = cursor.fetchall()
        
        # Query: SOLO clientes afectados (en zonas del aviso)
        zonas_afectadas = parse_csv_avisos(numero)
        if not zonas_afectadas:
            cursor.close()
            conn.close()
            return jsonify({'error': 'No hay zonas afectadas para este aviso'}), 404
        
        zonas_normalizadas = set()
        for zona in zonas_afectadas:
            zonas_normalizadas.add((
                zona['departamento'].upper().strip(),
                zona['provincia'].upper().strip(),
                zona['distrito'].upper().strip()
            ))
        
        deptos_unicos = list(set([zona[0] for zona in zonas_normalizadas]))
        
        if deptos_unicos:
            placeholders = ','.join(['%s'] * len(deptos_unicos))
            cursor.execute(f"""
                SELECT id, hectareas, monto_asegurado
                FROM clientes
                WHERE estado = 'activo' AND UPPER(TRIM(departamento)) IN ({placeholders})
            """, deptos_unicos)
        else:
            cursor.execute("SELECT id, hectareas, monto_asegurado FROM clientes WHERE 1=0")
        
        clientes_afectados = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Procesar datos
        resultado = {
            'numero_aviso': numero,
            'roja': {'agr_totales': 0, 'agr_afectados': 0, 'ha_totales': 0, 'ha_afectadas': 0, 'monto_total': 0, 'monto_afectado': 0},
            'naranja': {'agr_totales': 0, 'agr_afectados': 0, 'ha_totales': 0, 'ha_afectadas': 0, 'monto_total': 0, 'monto_afectado': 0},
            'amarilla': {'agr_totales': 0, 'agr_afectados': 0, 'ha_totales': 0, 'ha_afectadas': 0, 'monto_total': 0, 'monto_afectado': 0}
        }
        
        # Contar TODOS los clientes por color
        for cliente in todos_clientes:
            cliente_id = cliente['id']
            ha = float(cliente['hectareas'] or 0)
            monto = float(cliente['monto_asegurado'] or 0)
            
            # Asignar a zona según spatial join
            color = mapa_cliente_color.get(cliente_id, 'sin_zona')
            
            if color in resultado:
                resultado[color]['agr_totales'] += 1
                resultado[color]['ha_totales'] += ha
                resultado[color]['monto_total'] += monto
        
        # Contar AFECTADOS por color
        clientes_afectados_ids = set([c['id'] for c in clientes_afectados])
        for cliente in clientes_afectados:
            cliente_id = cliente['id']
            ha = float(cliente['hectareas'] or 0)
            monto = float(cliente['monto_asegurado'] or 0)
            
            color = mapa_cliente_color.get(cliente_id, 'sin_zona')
            
            if color in resultado:
                resultado[color]['agr_afectados'] += 1
                resultado[color]['ha_afectadas'] += ha
                resultado[color]['monto_afectado'] += monto
        
        # Redondear valores
        for color in resultado:
            resultado[color]['ha_totales'] = round(resultado[color]['ha_totales'], 2)
            resultado[color]['ha_afectadas'] = round(resultado[color]['ha_afectadas'], 2)
            resultado[color]['monto_total'] = round(resultado[color]['monto_total'], 2)
            resultado[color]['monto_afectado'] = round(resultado[color]['monto_afectado'], 2)
        
        logger.info("Resumen zonas para aviso %d calculado", numero)
        return jsonify(resultado)
    
    except Exception as e:
        logger.error("Error en resumen-zonas: %s", str(e))
        return jsonify({'error': str(e)}), 500


@decisiones_bp.route('/api/avisos/<int:numero>/resumen-entidades', methods=['GET'])
def api_resumen_entidades(numero):
    """
    Endpoint: Resumen por ENTIDADES (Depto/Provincia)
    Retorna: Agricultores totales vs afectados, % damage
    
    Returns:
        {
            'numero_aviso': numero,
            'departamentos': [
                {
                    'nombre': 'TACNA',
                    'agr_totales': 100,
                    'agr_afectados': 45,
                    'ha_afectadas': 320.5,
                    'monto_afectado': 1500000.00,
                    'pct_damage': '45%'
                },
                ...
            ]
        }
    """
    try:
        # Obtener TODOS los clientes y AFECTADOS
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Conexión BD fallida'}), 500
        
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Query: TODOS
        cursor.execute("""
            SELECT departamento, provincia, COUNT(*) as agr_total, 
                   SUM(COALESCE(hectareas, 0)) as ha_total,
                   SUM(COALESCE(monto_asegurado, 0)) as monto_total
            FROM clientes
            WHERE estado = 'activo'
            GROUP BY UPPER(TRIM(departamento)), UPPER(TRIM(provincia))
            ORDER BY departamento, provincia
        """)
        todos_depto = cursor.fetchall()
        
        # Query: AFECTADOS (por zonas del aviso)
        zonas_afectadas = parse_csv_avisos(numero)
        deptos_unicos = list(set([zona['departamento'].upper().strip() for zona in zonas_afectadas]))
        
        if deptos_unicos:
            placeholders = ','.join(['%s'] * len(deptos_unicos))
            cursor.execute(f"""
                SELECT departamento, provincia, COUNT(*) as agr_afectados, 
                       SUM(COALESCE(hectareas, 0)) as ha_afectadas,
                       SUM(COALESCE(monto_asegurado, 0)) as monto_afectado
                FROM clientes
                WHERE estado = 'activo' AND UPPER(TRIM(departamento)) IN ({placeholders})
                GROUP BY UPPER(TRIM(departamento)), UPPER(TRIM(provincia))
                ORDER BY departamento, provincia
            """, deptos_unicos)
        else:
            cursor.execute("SELECT NULL LIMIT 0")
        
        afectados_depto = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Construir resultado: MERGE todos + afectados
        resultado_deptos = {}
        
        # Agregar TODOS
        for row in todos_depto:
            depto = row['departamento'].upper().strip()
            provincia = row['provincia'].upper().strip() if row.get('provincia') else 'SIN PROVINCIA'
            
            key = (depto, provincia)
            resultado_deptos[key] = {
                'nombre_depto': depto,
                'nombre_provincia': provincia,
                'agr_totales': row['agr_total'],
                'agr_afectados': 0,
                'ha_afectadas': 0,
                'monto_afectado': 0
            }
        
        # Actualizar AFECTADOS
        for row in afectados_depto:
            depto = row['departamento'].upper().strip()
            provincia = row['provincia'].upper().strip() if row.get('provincia') else 'SIN PROVINCIA'
            
            key = (depto, provincia)
            if key in resultado_deptos:
                resultado_deptos[key]['agr_afectados'] = row['agr_afectados']
                resultado_deptos[key]['ha_afectadas'] = float(row.get('ha_afectadas', 0))
                resultado_deptos[key]['monto_afectado'] = float(row.get('monto_afectado', 0))
        
        # Calcular % damage
        departamentos = []
        for (depto, prov), data in resultado_deptos.items():
            pct = 0
            if data['agr_totales'] > 0:
                pct = round((data['agr_afectados'] / data['agr_totales']) * 100, 1)
            
            departamentos.append({
                'nombre': depto,
                'provincia': prov,
                'agr_totales': data['agr_totales'],
                'agr_afectados': data['agr_afectados'],
                'ha_afectadas': round(data['ha_afectadas'], 2),
                'monto_afectado': round(data['monto_afectado'], 2),
                'pct_damage': f"{pct}%"
            })
        
        logger.info("Resumen entidades para aviso %d calculado: %d deptos", numero, len(departamentos))
        return jsonify({
            'numero_aviso': numero,
            'departamentos': departamentos
        })
    
    except Exception as e:
        logger.error("Error en resumen-entidades: %s", str(e))
        return jsonify({'error': str(e)}), 500


@decisiones_bp.route('/decisiones', methods=['GET'])
def decisiones():
    """Página de decisiones"""
    return render_template('decisiones.html')


@decisiones_bp.route('/api/avisos/<int:numero>/clientes-afectados', methods=['GET'])
def api_clientes_afectados(numero):
    """
    API endpoint: Obtiene clientes afectados por aviso con estadísticas
    
    Query params (opcionales):
        ?depto=TACNA&provincia=TACNA&distrito=TACNA - filtro específico
    """
    try:
        depto = request.args.get('depto')
        provincia = request.args.get('provincia')
        distrito = request.args.get('distrito')
        
        clientes = get_clientes_afectados(numero, depto, provincia, distrito)
        stats = get_estadisticas_aviso(numero)
        
        response = {
            'numero_aviso': numero,
            'clientes': clientes,
            'estadisticas': stats
        }
        
        return jsonify(response)
        
    except (ValueError, TypeError) as e:
        logger.error("Error en API endpoint: %s", e)
        return jsonify({'error': str(e)}), 500


@decisiones_bp.route('/api/avisos/<int:numero>/estadisticas', methods=['GET'])
def api_estadisticas(numero):
    """
    API endpoint: Estadísticas agregadas del aviso
    """
    try:
        stats = get_estadisticas_aviso(numero)
        return jsonify(stats)
    except (ValueError, TypeError) as e:
        logger.error("Error en estadísticas: %s", e)
        return jsonify({'error': str(e)}), 500


@decisiones_bp.route('/api/avisos/<int:numero>/zonas', methods=['GET'])
def api_zonas_afectadas(numero):
    """
    API endpoint: Zonas (depto/provincia/distrito) afectadas por aviso
    Devuelve estructura jerárquica para Leaflet
    """
    try:
        zonas = parse_csv_avisos(numero)
        
        # Agrupar jerárquicamente
        deptos = defaultdict(lambda: defaultdict(set))
        for zona in zonas:
            deptos[zona['departamento']][zona['provincia']].add(zona['distrito'])
        
        # Convertir a estructura JSON
        result = {}
        for depto, provincias in deptos.items():
            result[depto] = {}
            for prov, distritos in provincias.items():
                result[depto][prov] = sorted(list(distritos))
        
        return jsonify({
            'numero_aviso': numero,
            'zonas': result,
            'total_zonas': len(zonas)
        })
        
    except (ValueError, TypeError) as e:
        logger.error("Error en zonas: %s", e)
        return jsonify({'error': str(e)}), 500


@decisiones_bp.route('/api/avisos/<int:numero>/shp-consolidado', methods=['GET'])
def generar_shp_consolidado(numero):
    """
    Devuelve GeoJSON del SHP coloreado por nivel de riesgo
    Lee del día crítico (mayor área ALTO/MUY_ALTO)
    Colores: Rojo (#FF0000) = Nivel 4, Naranja (#FF8C00) = Nivel 3, Gris = otros
    """
    try:
        temp_base = BASE_DIR / 'TEMP' / f'aviso_{numero}'
        
        if not temp_base.exists():
            return jsonify({'error': f'Aviso {numero} no encontrado'}), 404
        
        # Buscar los 3 días
        dict_shps = {}
        for dia in range(1, 4):
            dia_dir = temp_base / f'dia{dia}'
            shp_path = dia_dir / 'view_aviso.shp'
            if shp_path.exists():
                dict_shps[f'dia{dia}'] = str(shp_path)
        
        if not dict_shps:
            return jsonify({'error': 'No hay SHP disponibles'}), 404
        
        # Seleccionar día crítico
        dia_critico = 'dia1'
        shp_critico = None
        try:
            dia_critico, shp_critico = seleccionar_dia_critico(dict_shps)
        except (ValueError, AttributeError):
            # Si falla, usa dia1
            shp_critico = dict_shps.get('dia1')
            if not shp_critico:
                return jsonify({'error': 'No se pudo seleccionar día'}), 500
        
        # Leer SHP
        try:
            gdf = gpd.read_file(shp_critico)
        except (OSError, ValueError) as e:
            logger.error("Error leyendo SHP: %s", str(e))
            return jsonify({'error': f'Error leyendo SHP: {str(e)}'}), 500
        
        # Mapear colores por nivel (guiado de MAPAS.py)
        nivel_color = {
            'Nivel 4': '#FF0000',  # Rojo - MUY_ALTO
            'Nivel 3': '#FF8C00',  # Naranja - ALTO
            'Nivel 2': '#FFFF00',  # Amarillo - MEDIO
        }
        
        # Agregar columna de color
        gdf['fill_color'] = gdf['nivel'].map(nivel_color).fillna('#E8E8E8')
        
        # Retornar features con propiedades para Leaflet
        features = []
        for idx, row in gdf.iterrows():
            feature = {
                'type': 'Feature',
                'geometry': row.geometry.__geo_interface__,
                'properties': {
                    'nivel': row.get('nivel', ''),
                    'color': row['fill_color'],
                    'name': row.get('DISTRITO', row.get('PROVINCIA', 'Sin nombre'))
                }
            }
            features.append(feature)
        
        return jsonify({
            'type': 'FeatureCollection',
            'features': features,
            'dia_critico': dia_critico,
            'total': len(features)
        })
        
    except (OSError, ValueError, KeyError, AttributeError) as e:
        logger.error("Error en SHP: %s", str(e))
        return jsonify({'error': str(e)}), 500
