"""
Rutas de Utilidades - Páginas principales, dashboard, estadísticas y configuración
"""
from flask import Blueprint, render_template, request, jsonify, send_from_directory, send_file, make_response
from pathlib import Path
import os
import logging
import csv
from datetime import datetime, timedelta
import psycopg2
import psycopg2.extras
from io import StringIO

# Configuración
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / 'OUTPUT'
logger = logging.getLogger(__name__)

# Crear blueprint
utils_bp = Blueprint('utils', __name__, url_prefix='')


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def obtener_estadisticas():
    """Obtener estadísticas generales del sistema"""
    return {
        'avisos_activos': 3,
        'departamentos_afectados': 7,
        'agricultores_afectados': 1247,
        'agricultores_registrados': 15420,
        'mensajes_enviados': 2847,
        'cultivos_riesgo': 12,
        'probabilidad_evento': 85
    }


def obtener_evento_actual():
    """Obtener información del evento meteorológico actual"""
    return {
        'titulo': 'Lluvias Intensas y Vientos Fuertes',
        'tipo': 'Precipitaciones Pluviales',
        'vigencia': '22 Dic 2024 - 25 Dic 2024',
        'nivel_alerta': 'AMARILLO',
        'probabilidad': 85,
        'departamentos_afectados': ['Lima', 'Arequipa', 'Cusco', 'Piura', 'La Libertad', 'Lambayeque', 'Ica'],
        'cultivos_riesgo': ['Arroz', 'Maíz', 'Papa', 'Quinua', 'Algodón', 'Café', 'Cacao', 'Frijol', 'Trigo', 'Cebada', 'Palto', 'Mango'],
        'intensidad': 'Moderada a Fuerte',
        'descripcion': 'Se esperan precipitaciones de moderada a fuerte intensidad que podrían afectar las actividades agrícolas en las zonas indicadas.'
    }


def obtener_stats_whatsapp():
    """Estadísticas para página WhatsApp"""
    return {
        'total_contactos': 150,
        'enviados_hoy': 12,
        'pendientes': 3,
        'fallidos': 1
    }


def obtener_avisos_para_whatsapp():
    """Avisos disponibles para envío WhatsApp"""
    avisos = []
    
    if OUTPUT_DIR.exists():
        avisos_dirs = sorted([d for d in OUTPUT_DIR.iterdir() 
                            if d.is_dir() and d.name.startswith('aviso_')], 
                           key=lambda x: x.stat().st_mtime, reverse=True)[:10]
        
        for aviso_dir in avisos_dirs:
            numero = aviso_dir.name.replace('aviso_', '')
            mapas = len([f for f in aviso_dir.iterdir() if f.suffix == '.webp'])
            
            if mapas > 0:
                avisos.append({
                    'numero': numero,
                    'fecha': datetime.fromtimestamp(aviso_dir.stat().st_mtime).strftime('%d/%m/%Y'),
                    'departamentos': ['LIMA', 'LORETO']
                })
    
    return avisos


def obtener_historial_whatsapp():
    """Historial de envíos WhatsApp"""
    return []


def obtener_contactos_recientes():
    """Contactos recientes WhatsApp"""
    return []


# ============================================================================
# RUTAS - PÁGINAS WEB
# ============================================================================

@utils_bp.route('/', methods=['GET'])
def inicio():
    """Página de login - Inicio"""
    return render_template('inicio.html')


@utils_bp.route('/decisiones')
def decisiones():
    """Página de toma de decisiones - Centro de comando"""
    try:
        stats = obtener_estadisticas()
        evento_actual = obtener_evento_actual()
        
        return render_template('decisiones.html',
                             stats=stats,
                             evento_actual=evento_actual)
    except Exception as e:
        logger.error(f"Error en página decisiones: {str(e)}")
        return render_template('decisiones.html', stats={}, evento_actual=None)


@utils_bp.route('/difusion', methods=['GET'])
def difusion():
    """Página de Difusión - Envío automático de avisos meteorológicos"""
    try:
        stats_wa = obtener_stats_whatsapp()
        avisos_disponibles = obtener_avisos_para_whatsapp()
        historial = obtener_historial_whatsapp()
        contactos = obtener_contactos_recientes()
        
        return render_template('difusion.html', 
                             stats=stats_wa,
                             avisos_disponibles=avisos_disponibles,
                             historial_envios=historial,
                             contactos_recientes=contactos)
    except Exception as e:
        logger.error(f"Error en página difusion: {str(e)}")
        return render_template('difusion.html', 
                             stats={}, avisos_disponibles=[], 
                             historial_envios=[], contactos_recientes=[])


@utils_bp.route('/mensajeria', methods=['GET'])
def mensajeria():
    """Página de Mensajería - Envío general de mensajes (SMS, Email, WhatsApp)"""
    try:
        return render_template('mensajeria.html')
    except Exception as e:
        logger.error(f"Error en página mensajeria: {str(e)}")
        return render_template('mensajeria.html')


@utils_bp.route('/configuracion', methods=['GET'])
def configuracion():
    """Página de configuración"""
    return render_template('configuracion.html')


@utils_bp.route('/logs', methods=['GET'])
def logs():
    """Página de logs del sistema"""
    return render_template('logs.html')


# ============================================================================
# RUTAS API - ESTADÍSTICAS Y ESTADO
# ============================================================================

@utils_bp.route('/api/stats', methods=['GET'])
def api_stats():
    """API endpoint para estadísticas"""
    try:
        stats = obtener_estadisticas()
        return jsonify(stats), 200
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {str(e)}")
        return jsonify({'error': str(e)}), 500


@utils_bp.route('/health', methods=['GET'])
def health():
    """Endpoint de salud - verifica que la API está funcionando"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    }), 200


@utils_bp.route('/status', methods=['GET'])
def status():
    """Endpoint para verificar estado general de la API"""
    try:
        temp_dir = BASE_DIR / "TEMP"
        output_dir = BASE_DIR / "OUTPUT"
        
        return jsonify({
            'status': 'ok',
            'temp_dir': {
                'existe': temp_dir.exists(),
                'ruta': str(temp_dir)
            },
            'output_dir': {
                'existe': output_dir.exists(),
                'ruta': str(output_dir),
                'avisos_procesados': len([d for d in output_dir.iterdir() if d.is_dir()]) if output_dir.exists() else 0
            },
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"Error en status: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        }), 500


# ============================================================================
# RUTAS API - ARCHIVOS Y OTROS
# ============================================================================

@utils_bp.route('/OUTPUT/<path:filepath>', methods=['GET'])
def serve_output(filepath):
    """Servir archivos estáticos desde OUTPUT"""
    try:
        return send_from_directory(str(OUTPUT_DIR), filepath, as_attachment=True)
    except Exception as e:
        logger.error(f"Error sirviendo archivo {filepath}: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Archivo no encontrado'}), 404


@utils_bp.route('/api/avisos/<int:numero>/imagenes', methods=['GET'])
def api_avisos_imagenes(numero):
    """API para obtener imágenes y CSV de afectados (para n8n)"""
    try:
        carpeta = BASE_DIR / 'OUTPUT' / f'aviso_{numero}'
        if not carpeta.exists():
            return jsonify({
                'status': 'error',
                'message': f'No hay datos para el aviso {numero}'
            }), 404
        
        imagenes = []
        for archivo in sorted(carpeta.glob('*.webp')):
            imagenes.append({
                'nombre': archivo.name,
                'url': f'/OUTPUT/aviso_{numero}/{archivo.name}',
                'ruta_local': str(archivo)
            })
        
        archivos_csv = []
        for csv_file in carpeta.glob('*.csv'):
            archivos_csv.append({
                'nombre': csv_file.name,
                'url': f'/OUTPUT/aviso_{numero}/{csv_file.name}',
                'ruta_local': str(csv_file),
                'tipo': 'departamentos' if 'departamentos' in csv_file.name else 'provincias'
            })
        
        return jsonify({
            'status': 'success',
            'numero_aviso': numero,
            'total_imagenes': len(imagenes),
            'total_afectados': len(archivos_csv),
            'imagenes': imagenes,
            'archivos_csv': archivos_csv,
            'mensaje': f'Aviso {numero}: {len(imagenes)} imágenes, {len(archivos_csv)} CSV(s) con departamentos/provincias'
        })
    except Exception as e:
        logger.error(f"Error al obtener imágenes: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@utils_bp.route('/avisos/<int:numero_aviso>', methods=['GET'])
def obtener_aviso(numero_aviso):
    """Endpoint para obtener detalles de un aviso ya procesado"""
    try:
        output_dir = OUTPUT_DIR / f"aviso_{numero_aviso}"
        
        if not output_dir.exists():
            return jsonify({
                'status': 'not_found',
                'numero_aviso': numero_aviso,
                'existe': False,
                'message': f'Aviso {numero_aviso} no encontrado'
            }), 404
        
        mapas = []
        archivos_adicionales = []
        
        for archivo in output_dir.iterdir():
            if archivo.suffix == '.webp':
                mapas.append(archivo.name)
            elif archivo.suffix == '.csv':
                archivos_adicionales.append(archivo.name)
        
        return jsonify({
            'status': 'success',
            'numero_aviso': numero_aviso,
            'existe': True,
            'output_dir': str(output_dir),
            'mapas': sorted(mapas),
            'archivos_adicionales': sorted(archivos_adicionales)
        }), 200
    
    except Exception as e:
        logger.error(f"Error obteniendo aviso: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        }), 500


# ============================================================================
# MANEJADORES DE ERRORES
# ============================================================================


# ============================================================================
# RUTAS - API ENDPOINTS
# ============================================================================

@utils_bp.route('/api/difusion/clientes/<int:numero>', methods=['GET'])
def api_clientes_afectados(numero):
    """API para obtener estadísticas de clientes afectados por aviso y nivel"""
    try:
        aviso_dir = OUTPUT_DIR / f'aviso_{numero}'
        
        if not aviso_dir.exists():
            return jsonify({
                'success': False,
                'error': f'Aviso {numero} no encontrado'
            }), 404
        
        stats = {
            'rojo': 0,
            'naranja': 0,
            'amarillo': 0,
            'total': 0
        }
        
        # Leer CSVs de los 3 días disponibles
        for dia in range(1, 4):
            csv_path = aviso_dir / f'clientes_por_nivel_dia{dia}.csv'
            
            if csv_path.exists():
                try:
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            nivel = row.get('nivel', '').lower().strip()
                            
                            if nivel == 'rojo':
                                stats['rojo'] += 1
                            elif nivel == 'naranja':
                                stats['naranja'] += 1
                            elif nivel == 'amarillo':
                                stats['amarillo'] += 1
                
                except Exception as e:
                    logger.warning(f"Error leyendo CSV dia{dia}: {str(e)}")
        
        stats['total'] = stats['rojo'] + stats['naranja'] + stats['amarillo']
        
        return jsonify({
            'success': True,
            'numero': numero,
            'stats': stats
        }), 200
    
    except Exception as e:
        logger.error(f"Error en API clientes afectados: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# ENDPOINT: Obtener entidades de la BD
# ============================================================================
@utils_bp.route('/api/entidades', methods=['GET'])
def api_entidades():
    """Obtiene lista de entidades desde la BD"""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD')
        )
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute("SELECT id, nombre FROM entidades ORDER BY nombre")
        entidades = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': entidades
        }), 200
    
    except Exception as e:
        logger.error(f"Error obteniendo entidades: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# ENDPOINT: Exportar CSV de clientes por aviso
# ============================================================================
@utils_bp.route('/api/difusion/clientes/export/<int:numero>', methods=['GET'])
def api_export_clientes(numero):
    """Exporta CSV con clientes afectados por un aviso - Cruza datos de CSV + BD"""
    try:
        output_path = OUTPUT_DIR / f'aviso_{numero}'
        
        # 1. Recopilar IDs y niveles de clientes del CSV
        clientes_mapping = {}  # {id: {'nivel': 'Rojo', ...}}
        
        for dia in range(1, 4):
            csv_path = output_path / f'clientes_por_nivel_dia{dia}.csv'
            
            if csv_path.exists():
                try:
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            cliente_id = row.get('id')
                            nivel = row.get('nivel', '').lower().strip()
                            
                            if cliente_id and cliente_id not in clientes_mapping:
                                clientes_mapping[cliente_id] = {
                                    'nivel': nivel,
                                    'latitud': row.get('latitud', ''),
                                    'longitud': row.get('longitud', '')
                                }
                
                except Exception as e:
                    logger.warning(f"Error leyendo CSV dia{dia}: {str(e)}")
        
        if not clientes_mapping:
            return jsonify({
                'success': False,
                'error': f'No se encontraron datos para aviso {numero}'
            }), 404
        
        # 2. Obtener datos completos de la BD
        try:
            conn = psycopg2.connect(
                host=os.getenv('DB_HOST'),
                database=os.getenv('DB_NAME'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD')
            )
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Obtener todos los clientes de la BD con JOINs a entidades y cultivos
            cliente_ids = tuple(clientes_mapping.keys())
            placeholders = ','.join(['%s'] * len(cliente_ids))
            
            query = f"""
                SELECT 
                    c.id, 
                    CONCAT(c.nombre, ' ', c.apellido) as nombre,
                    c.telefono, 
                    c.correo, 
                    c.departamento, 
                    c.provincia, 
                    c.distrito,
                    c.hectareas,
                    tc.nombre as cultivo,
                    c.monto_asegurado,
                    c.fecha_registro as fecha,
                    e.nombre as entidad
                FROM clientes c
                LEFT JOIN tabla_cultivos tc ON c.cultivo_id = tc.id
                LEFT JOIN entidades e ON c.entidad_id = e.id
                WHERE c.id IN ({placeholders})
                ORDER BY c.id
            """
            
            cursor.execute(query, cliente_ids)
            clientes_bd = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error consultando BD: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'Error en BD: {str(e)}'
            }), 500
        
        # 3. Combinar datos CSV + BD
        clientes_completos = []
        
        for cliente in clientes_bd:
            cliente_id = str(cliente['id'])
            
            if cliente_id in clientes_mapping:
                cliente_data = dict(cliente)
                cliente_data['nivel'] = clientes_mapping[cliente_id]['nivel']
                clientes_completos.append(cliente_data)
        
        if not clientes_completos:
            return jsonify({
                'success': False,
                'error': 'No se encontraron clientes con datos completos'
            }), 404
        
        # 4. Crear CSV en memoria
        output = StringIO()
        
        # Definir campos para exportación (en orden específico)
        fields = ['id', 'nombre', 'telefono', 'correo', 'departamento', 'provincia', 'distrito', 
                  'hectareas', 'cultivo', 'nivel', 'entidad', 'monto_asegurado', 'fecha']
        
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(clientes_completos)
        
        # 5. Preparar respuesta
        csv_string = output.getvalue()
        filename = f'clientes_aviso_{numero}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        # Retornar como descarga
        response = make_response(csv_string)
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        
        logger.info(f"✓ CSV exportado: {filename} ({len(clientes_completos)} registros)")
        
        return response, 200
    
    except Exception as e:
        logger.error(f"Error exportando CSV: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@utils_bp.errorhandler(404)
def not_found(error):
    """Manejador de rutas no encontradas"""
    return jsonify({
        'status': 'error',
        'message': 'Ruta no encontrada'
    }), 404


@utils_bp.errorhandler(500)
def internal_error(error):
    """Manejador de errores internos"""
    logger.error(f"Error interno: {str(error)}")
    return jsonify({
        'status': 'error',
        'message': 'Error interno del servidor'
    }), 500
