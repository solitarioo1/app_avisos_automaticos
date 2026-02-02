"""
Rutas de Utilidades - Páginas principales, dashboard, estadísticas y configuración
"""
from flask import Blueprint, render_template, request, jsonify, send_from_directory
from pathlib import Path
import os
import logging
from datetime import datetime, timedelta

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


@utils_bp.route('/dashboard', methods=['GET'])
def dashboard_page():
    """Dashboard principal después del login"""
    stats = {
        'avisos_activos': 0,
        'departamentos_afectados': 0,
        'agricultores_afectados': 0,
        'cultivos_riesgo': 0
    }
    evento_actual = None
    avisos_recientes = []
    mapas_recientes = []
    return render_template('dashboard.html', stats=stats, evento_actual=evento_actual, 
                         avisos_recientes=avisos_recientes, mapas_recientes=mapas_recientes)


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


@utils_bp.route('/whatsapp', methods=['GET'])
def whatsapp():
    """Página de WhatsApp masivo"""
    try:
        stats_wa = obtener_stats_whatsapp()
        avisos_disponibles = obtener_avisos_para_whatsapp()
        historial = obtener_historial_whatsapp()
        contactos = obtener_contactos_recientes()
        
        return render_template('whatsapp.html', 
                             stats=stats_wa,
                             avisos_disponibles=avisos_disponibles,
                             historial_envios=historial,
                             contactos_recientes=contactos)
    except Exception as e:
        logger.error(f"Error en página whatsapp: {str(e)}")
        return render_template('whatsapp.html', 
                             stats={}, avisos_disponibles=[], 
                             historial_envios=[], contactos_recientes=[])


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
