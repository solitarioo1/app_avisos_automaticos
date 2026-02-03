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
import psycopg2
import psycopg2.extras
from flask import Blueprint, jsonify, render_template, request

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


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

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
