"""
Rutas de Decisiones - API endpoints para toma de decisiones
Integra datos de clientes BD con CSV avisos y calcula estadísticas
"""
import csv
import logging
import sys
import traceback
from collections import Counter
from pathlib import Path

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
    from CONFIG.db import (
        get_connection,
        obtener_clientes_por_nivel_desde_bd
    )
except ImportError:
    # Fallback: usar conexión directa
    get_connection = None
    obtener_clientes_por_nivel_desde_bd = None

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
    Lee zonas afectadas: primero intenta BD, luego fallback a CSV
    """
    def normalize_zona(z):
        """Normaliza zona de cualquier formato"""
        return {
            'departamento': (z.get('departamento') or '').upper().strip(),
            'provincia': (z.get('provincia') or '').upper().strip(),
            'distrito': (z.get('distrito') or '').upper().strip()
        }
    
    # Intentar desde BD primero
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(
                "SELECT DISTINCT departamento, provincia, distrito FROM aviso_zonas_afectadas WHERE numero_aviso = %s",
                (numero_aviso,)
            )
            zonas_rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            if zonas_rows:
                result = [normalize_zona(z) for z in zonas_rows]
                logger.info("Zonas desde BD: %d zonas", len(result))
                return result
    except Exception as e:
        logger.warning("Error leyendo zonas desde BD: %s", str(e))
        traceback.print_exc()
    
    # Fallback: leer CSV
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
                    distritos.append(normalize_zona(row))
        logger.info("CSV parseado: %d distritos para aviso %d", len(distritos), numero_aviso)
        return distritos
    except OSError as e:
        logger.error("Error leyendo CSV: %s", str(e))
        return []


def get_clientes_afectados(numero_aviso, depto=None, provincia=None, distrito=None):
    """
    Consulta BD clientes desde vista y filtra por aviso + zona afectada
    
    Retorna los clientes clasificados por nivel (vista v_clientes_por_aviso_completo)
    """
    try:
        # Obtener clientes clasificados desde BD (vista con nivel de riesgo)
        df_clientes = obtener_clientes_por_nivel_desde_bd(numero_aviso)
        
        if df_clientes is None or len(df_clientes) == 0:
            return {
                'total_agricultores': 0,
                'agricultores': [],
                'cultivos': {},
                'total_hectareas': 0,
                'total_monto_asegurado': 0,
                'financieras': {}
            }
        
        # Obtener zonas afectadas
        zonas_afectadas = parse_csv_avisos(numero_aviso)
        deptos_afectados = list(set([zona['departamento'].upper().strip() for zona in zonas_afectadas]))
        
        # Filtrar DataFrame por zonas afectadas
        agricultores = []
        for _, row in df_clientes.iterrows():
            depto_row = (str(row.get('departamento') or '')).upper().strip()
            
            # Filtro 1: Solo departamentos afectados
            if depto_row not in deptos_afectados:
                continue
            
            # Filtro 2: Filtros opcionales (si se proporcionan)
            if depto and depto.upper().strip() != depto_row:
                continue
            if provincia:
                prov_row = (str(row.get('provincia') or '')).upper().strip()
                if provincia.upper().strip() != prov_row:
                    continue
            if distrito:
                dist_row = (str(row.get('distrito') or '')).upper().strip()
                if distrito.upper().strip() != dist_row:
                    continue
            
            # Convertir row a dict
            agr_dict = {
                'id': row.get('cliente_id'),
                'nombre': row.get('nombre', ''),
                'apellido': row.get('apellido', ''),
                'dni_ruc': row.get('dni_ruc', ''),
                'latitud': row.get('latitud'),
                'longitud': row.get('longitud'),
                'cultivo_id': row.get('cultivo_id'),
                'cultivo': row.get('cultivo', ''),
                'hectareas': float(row.get('hectareas') or 0),
                'monto_asegurado': float(row.get('monto_asegurado') or 0),
                'distrito': row.get('distrito', ''),
                'provincia': row.get('provincia', ''),
                'departamento': depto_row,
                'nivel': row.get('nivel', ''),
                'entidad_nombre': row.get('entidad_nombre', '')
            }
            agricultores.append(agr_dict)
        
        # Calcular agregaciones
        cultivos_counter = Counter()
        total_hectareas = 0
        total_monto = 0
        
        for agr in agricultores:
            if agr.get('cultivo_id'):
                cultivos_counter[str(agr.get('cultivo', 'N/A'))] += 1
            total_hectareas += agr.get('hectareas', 0)
            total_monto += agr.get('monto_asegurado', 0)
        
        logger.info("Clientes afectados para aviso %d: %d (deptos: %s)",
                    numero_aviso, len(agricultores), deptos_afectados[:3])
        
        return {
            'total_agricultores': len(agricultores),
            'agricultores': agricultores,
            'cultivos': dict(cultivos_counter),
            'total_hectareas': round(total_hectareas, 2),
            'total_monto_asegurado': round(total_monto, 2),
            'financieras': {}
        }
    
    except Exception as e:
        logger.error("Error en get_clientes_afectados: %s", str(e))
        return {
            'total_agricultores': 0,
            'agricultores': [],
            'cultivos': {},
            'total_hectareas': 0,
            'total_monto_asegurado': 0,
            'financieras': {}
        }


def get_estadisticas_aviso(numero_aviso):
    """
    Estadísticas del aviso usando v_estadisticas_aviso (una sola query)
    """
    try:
        conn = get_db_connection()
        if not conn:
            return {}

        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "SELECT * FROM v_estadisticas_aviso WHERE numero_aviso = %s",
            (numero_aviso,)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return {}

        color = (row['color'] or '').lower()
        total = int(row['total_clientes'] or 0)
        afectados = (int(row['clientes_nivel_rojo']    or 0) +
                     int(row['clientes_nivel_naranja']  or 0) +
                     int(row['clientes_nivel_amarillo'] or 0))

        return {
            'color': color,
            'critico': {
                'nivel': 'CRÍTICO' if color == 'rojo' else '',
                'count': afectados if color == 'rojo' else 0
            },
            'alto_riesgo': {
                'nivel': 'ALTO RIESGO' if color == 'naranja' else '',
                'count': afectados if color == 'naranja' else 0
            },
            'agricultores_total': total,
            'poliza_total':    float(row['total_monto_asegurado'] or 0),
            'hectareas_total': float(row['total_hectareas']       or 0)
        }

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



@decisiones_bp.route('/api/avisos/<int:numero>/kpis-entidades', methods=['GET'])
def get_kpis_entidades(numero):
    """TOP 5 entidades con más agricultores afectados (Rojo/Naranja/Amarillo)"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Sin conexión a BD'}), 500

        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("""
            SELECT
                entidad_id,
                entidad_nombre,
                COUNT(*)                        AS agricultores,
                COALESCE(SUM(hectareas),       0) AS hectareas,
                COALESCE(SUM(monto_asegurado), 0) AS monto
            FROM v_clientes_por_aviso_completo
            WHERE numero_aviso = %s
              AND nivel IN ('Rojo', 'Naranja', 'Amarillo')
              AND UPPER(departamento) IN (
                    SELECT DISTINCT UPPER(departamento)
                    FROM aviso_zonas_afectadas
                    WHERE numero_aviso = %s
              )
            GROUP BY entidad_id, entidad_nombre
            ORDER BY agricultores DESC
            LIMIT 5
        """, (numero, numero))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if not rows:
            return jsonify({'error': f'No hay clientes para aviso {numero}'}), 404

        entidades_list = []
        total_monto = sum(float(r['monto'] or 0) for r in rows)
        for r in rows:
            monto = float(r['monto'] or 0)
            entidades_list.append({
                'entidad_id':   r['entidad_id'],
                'nombre':       r['entidad_nombre'],
                'agricultores': int(r['agricultores']),
                'hectareas':    round(float(r['hectareas'] or 0), 2),
                'monto':        round(monto, 2),
                'pct_damage':   round(monto / total_monto * 100, 1) if total_monto > 0 else 0
            })

        return jsonify({'numero_aviso': numero, 'entidades': entidades_list})
    except Exception as e:
        logger.error("Error SQL entidades: %s", str(e))
        return jsonify({'error': str(e)}), 500


@decisiones_bp.route('/api/avisos/<int:numero>/kpis-cultivos', methods=['GET'])
def get_kpis_cultivos(numero):
    """TOP 5 cultivos más afectados (Rojo/Naranja/Amarillo en deptos afectados)"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Sin conexión a BD'}), 500

        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("""
            SELECT
                cultivo_id,
                cultivo                         AS cultivo_nombre,
                UPPER(departamento)             AS departamento,
                COUNT(*)                        AS agricultores,
                COALESCE(SUM(hectareas),       0) AS hectareas,
                COALESCE(SUM(monto_asegurado), 0) AS monto
            FROM v_clientes_por_aviso_completo
            WHERE numero_aviso = %s
              AND nivel IN ('Rojo', 'Naranja', 'Amarillo')
              AND UPPER(departamento) IN (
                    SELECT DISTINCT UPPER(departamento)
                    FROM aviso_zonas_afectadas
                    WHERE numero_aviso = %s
              )
            GROUP BY cultivo_id, cultivo, UPPER(departamento)
            ORDER BY agricultores DESC
            LIMIT 5
        """, (numero, numero))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if not rows:
            return jsonify({'error': f'No hay clientes para aviso {numero}'}), 404

        cultivos_list = [{
            'cultivo_id':     r['cultivo_id'],
            'cultivo_nombre': r['cultivo_nombre'],
            'departamento':   r['departamento'],
            'agricultores':   int(r['agricultores']),
            'hectareas':      round(float(r['hectareas'] or 0), 2),
            'monto':          round(float(r['monto']    or 0), 2)
        } for r in rows]

        logger.info("Cultivos TOP 5 para aviso %d: %d cultivos", numero, len(cultivos_list))
        return jsonify({'numero_aviso': numero, 'cultivos': cultivos_list})

    except Exception as e:
        logger.error("Error calculando KPIs cultivos: %s", str(e))
        return jsonify({'error': str(e)}), 500


@decisiones_bp.route('/api/avisos/<int:numero>/kpis', methods=['GET'])
def get_kpis(numero):
    """KPIs principales usando directamente la vista v_estadisticas_aviso"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Sin conexión a BD'}), 500

        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "SELECT * FROM v_estadisticas_aviso WHERE numero_aviso = %s",
            (numero,)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return jsonify({'error': f'No hay datos para aviso {numero}'}), 404

        totales   = int(row['total_clientes'] or 0)
        afectados = int((row['clientes_nivel_rojo']     or 0) +
                        (row['clientes_nivel_naranja']   or 0) +
                        (row['clientes_nivel_amarillo']  or 0))
        porcentaje = round(afectados / totales * 100, 1) if totales > 0 else 0

        zonas_por_color = {
            'Rojo': {
                'agricultores': int(row['clientes_nivel_rojo']    or 0),
                'hectareas':  float(row['hectareas_nivel_rojo']   or 0),
                'poliza':     float(row['monto_nivel_rojo']       or 0)
            },
            'Naranja': {
                'agricultores': int(row['clientes_nivel_naranja']  or 0),
                'hectareas':  float(row['hectareas_nivel_naranja'] or 0),
                'poliza':     float(row['monto_nivel_naranja']     or 0)
            },
            'Amarillo': {
                'agricultores': int(row['clientes_nivel_amarillo']  or 0),
                'hectareas':  float(row['hectareas_nivel_amarillo'] or 0),
                'poliza':     float(row['monto_nivel_amarillo']     or 0)
            },
            'Verde': {
                'agricultores': int(row['clientes_nivel_verde']    or 0),
                'hectareas':  float(row['hectareas_nivel_verde']   or 0),
                'poliza':     float(row['monto_nivel_verde']       or 0)
            }
        }

        return jsonify({
            'agricultores_totales':   totales,
            'agricultores_afectados': afectados,
            'porcentaje_afectacion':  porcentaje,
            'hectareas_totales':  float(row['total_hectareas']  or 0),
            'hectareas_afectadas': round(
                float(row['hectareas_nivel_rojo']    or 0) +
                float(row['hectareas_nivel_naranja'] or 0) +
                float(row['hectareas_nivel_amarillo']or 0), 2),
            'poliza_total':    float(row['total_monto_asegurado'] or 0),
            'poliza_afectados': round(
                float(row['monto_nivel_rojo']    or 0) +
                float(row['monto_nivel_naranja'] or 0) +
                float(row['monto_nivel_amarillo']or 0), 2),
            'zonas_por_color': zonas_por_color
        })

    except Exception as e:
        logger.error("Error calculando KPIs: %s", str(e))
        return jsonify({'error': str(e)}), 500