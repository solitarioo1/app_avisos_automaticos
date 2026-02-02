"""
API Flask para procesamiento automático de avisos SENAMHI
Interfaz HTTP para integración con n8n + Dashboard Web
Versión 2.0 - Refactorizada con Blueprints
"""

from flask import Flask, request, jsonify
from pathlib import Path
import sys
import os
import logging
from datetime import datetime
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Agregar directorios al path
sys.path.insert(0, str(Path(__file__).parent))

# Importaciones condicionales
try:
    from procesar_aviso import procesar_aviso
    PROCESAR_AVISO_DISPONIBLE = True
except ImportError as e:
    logger.warning(f"Módulo procesar_aviso no disponible: {e}")
    PROCESAR_AVISO_DISPONIBLE = False
    def procesar_aviso(*args, **kwargs):
        return {"success": False, "error": "Módulo no disponible"}

try:
    from CONFIG.db import obtener_aviso_por_numero
    DB_DISPONIBLE = True
except ImportError as e:
    logger.warning(f"Módulo CONFIG.db no disponible: {e}")
    DB_DISPONIBLE = False
    def obtener_aviso_por_numero(numero):
        return None

# Inicializar Flask
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.config['DONT_RELOAD_REGEX'] = r'(\.git|__pycache__|\.pytest_cache|node_modules|TEMP|OUTPUT|\.egg-info)'

# Rutas base
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / os.getenv('OUTPUT_DIR', 'OUTPUT')
DOMAIN = os.getenv('DOMAIN', 'https://mapas.miagentepersonal.me')

# Diccionario global para procesos activos
active_processes = {}

# ============================================================================
# REGISTRAR BLUEPRINTS - Modularización de rutas
# ============================================================================

from routes.avisos import avisos_bp
from routes.mapas import mapas_bp
from routes.utils import utils_bp

# Registrar blueprints (cada blueprint contiene sus propias rutas)
app.register_blueprint(avisos_bp)
app.register_blueprint(mapas_bp)
app.register_blueprint(utils_bp)

# ============================================================================
# ENDPOINT PRINCIPAL - PROCESAR AVISO (Integración con n8n)
# ============================================================================

@app.route('/procesar-aviso', methods=['POST'])
@app.route('/api/procesar-aviso', methods=['POST'])
def procesar_aviso_endpoint():
    """
    Endpoint principal para procesar avisos SENAMHI
    
    Body esperado:
    {
        "numero_aviso": 447,
        "desde_bd": false,
        "json_path": "/path/to/aviso.json"  (opcional)
    }
    
    Respuesta exitosa:
    {
        "status": "success",
        "numero_aviso": 447,
        "output_dir": "/path/to/OUTPUT/aviso_447",
        "mapas": ["departamento1.webp", "departamento2.webp"],
        "archivos_adicionales": ["provincias_afectadas.csv", "distritos_afectados.csv"],
        "timestamp": "2026-01-01T12:00:00"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'JSON body requerido'}), 400
        
        numero_aviso = data.get('numero_aviso')
        if not numero_aviso:
            return jsonify({'status': 'error', 'message': 'Campo "numero_aviso" requerido'}), 400
        
        try:
            numero_aviso = int(numero_aviso)
        except (ValueError, TypeError):
            return jsonify({'status': 'error', 'message': f'numero_aviso debe ser un entero, recibido: {numero_aviso}'}), 400
        
        desde_bd = data.get('desde_bd', False)
        json_path = data.get('json_path', None)
        
        if json_path:
            json_path = Path(json_path)
            if not json_path.exists():
                return jsonify({'status': 'error', 'message': f'Archivo JSON no encontrado: {json_path}'}), 400
        
        if desde_bd:
            aviso_bd = obtener_aviso_por_numero(numero_aviso)
            if not aviso_bd:
                return jsonify({'status': 'error', 'message': f'Aviso {numero_aviso} no encontrado en base de datos'}), 404
        
        logger.info(f"Iniciando procesamiento de aviso {numero_aviso} (desde_bd={desde_bd})")
        
        if not PROCESAR_AVISO_DISPONIBLE:
            return jsonify({'status': 'error', 'message': 'Módulo de procesamiento no disponible. Verifique las dependencias (geopandas, etc.)'}), 503
        
        resultado = procesar_aviso(numero_aviso, desde_bd)
        
        output_dir = OUTPUT_DIR / f"aviso_{numero_aviso}"
        mapas = []
        archivos_adicionales = []
        
        if output_dir.exists():
            for archivo in output_dir.iterdir():
                if archivo.suffix == '.webp':
                    mapas.append(archivo.name)
                elif archivo.suffix == '.csv':
                    archivos_adicionales.append(archivo.name)
        
        logger.info(f"Aviso {numero_aviso} procesado exitosamente. Mapas: {len(mapas)}")
        
        mapas_urls = {}
        for mapa in mapas:
            mapa_relative = f"aviso_{numero_aviso}/{mapa}"
            mapas_urls[mapa] = f"{DOMAIN}/OUTPUT/{mapa_relative}"
        
        return jsonify({
            'status': 'success',
            'numero_aviso': numero_aviso,
            'output_dir': str(output_dir),
            'mapas': sorted(mapas),
            'mapas_urls': mapas_urls,
            'archivos_adicionales': sorted(archivos_adicionales),
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"Error procesando aviso: {str(e)}", exc_info=True)
        return jsonify({'status': 'error', 'message': f'Error al procesar aviso: {str(e)}'}), 500


# ============================================================================
# MANEJADORES DE ERRORES
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Manejador de rutas no encontradas"""
    return jsonify({'status': 'error', 'message': 'Ruta no encontrada'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Manejador de errores internos"""
    logger.error(f"Error interno: {str(error)}")
    return jsonify({'status': 'error', 'message': 'Error interno del servidor'}), 500


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == '__main__':
    # Crear directorios si no existen
    (BASE_DIR / "TEMP").mkdir(exist_ok=True)
    (BASE_DIR / "OUTPUT").mkdir(exist_ok=True)
    
    logger.info("🚀 Iniciando servidor Flask - Avisos SENAMHI")
    logger.info(f"📁 Directorio base: {BASE_DIR}")
    logger.info(f"📊 Directorio de salida: {OUTPUT_DIR}")
    logger.info(f"🌐 Dominio: {DOMAIN}")
    
    # Ejecutar servidor
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        use_reloader=False,
        threaded=True
    )
