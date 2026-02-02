"""
Rutas de Decisiones - API endpoints para toma de decisiones
Integra datos de clientes BD con CSV avisos y calcula estadísticas
"""
import csv
import logging
import os
from pathlib import Path
from collections import defaultdict, Counter

from flask import Blueprint, jsonify, render_template, request
import psycopg2
import psycopg2.extras

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / 'OUTPUT'
logger = logging.getLogger(__name__)

decisiones_bp = Blueprint('decisiones', __name__, url_prefix='')


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def get_db_connection():
    """Obtener conexión a PostgreSQL"""
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )
        return conn
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
        
        # Construir query con filtros
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Filtro de zona desde CSV
        zone_conditions = []
        zone_params = []
        
        for depto_csv, prov_csv, dist_csv in zonas_normalizadas:
            zone_conditions.append(
                "(UPPER(TRIM(departamento)) = %s AND "
                "UPPER(TRIM(provincia)) = %s AND "
                "UPPER(TRIM(distrito)) = %s)"
            )
            zone_params.extend([depto_csv, prov_csv, dist_csv])
        
        # Construir cláusula WHERE: (zone1) OR (zone2) OR ... AND (optional filters)
        where_parts = []
        all_params = []
        
        # Agregar condiciones de zonas
        if zone_conditions:
            zone_clause = " OR ".join(zone_conditions)
            where_parts.append(f"({zone_clause})")
            all_params.extend(zone_params)
        
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
        
        agricultores = cursor.fetchall()
        
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
        
        logger.info("Clientes obtenidos para aviso %d: %d registros", numero_aviso, len(agricultores_list))
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
