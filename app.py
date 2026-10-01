"""
API Flask para procesamiento automático de avisos SENAMHI
Interfaz HTTP para integración con n8n + Dashboard Web
Versión 2.0 - Refactorizada con Blueprints
"""

from flask import Flask, request, jsonify
from flask_login import LoginManager
from flask_compress import Compress
from pathlib import Path
import sys
import os
import logging
import threading
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
# Comprime las respuestas (los geojson de capas de riesgo pesan varios MB sin esto).
app.config['COMPRESS_MIMETYPES'] = ['application/json', 'text/html', 'text/css', 'application/javascript']
Compress(app)

# Flask-Login
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-testing-only')
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Inicia sesión para continuar'
login_manager.login_message_category = 'warning'

from routes.auth import get_user
@login_manager.user_loader
def load_user(user_id: str):
    return get_user(user_id)

# Rutas base
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / os.getenv('OUTPUT_DIR', 'OUTPUT')
DOMAIN = os.getenv('DOMAIN', 'https://mapas.intismart.com')

# Diccionario global para procesos activos
active_processes = {}

# ============================================================================
# REGISTRAR BLUEPRINTS - Modularización de rutas
# ============================================================================

from routes.avisos import avisos_bp
from routes.mapas import mapas_bp
from routes.utils import utils_bp
from routes.decisiones import decisiones_bp
from routes.mapas_shp import mapas_shp_bp
from routes.areas import areas_bp
from routes.difusion import difusion_bp
from routes.mensajeria import mensajeria_bp
from routes.auth import auth_bp
from routes.seguimiento_cultivo import seguimiento_cultivo_bp
from routes.evaluacion_riesgo import evaluacion_riesgo_bp
from routes.capas_riesgo import capas_riesgo_bp
from routes.clasificar_cliente import clasificar_cliente_bp
from routes.mapa_calor_siniestros import mapa_calor_siniestros_bp
from routes.siniestros_agricultor import siniestros_agricultor_bp

# Registrar blueprints (cada blueprint contiene sus propias rutas)
app.register_blueprint(auth_bp)
app.register_blueprint(avisos_bp)
app.register_blueprint(mapas_bp)
app.register_blueprint(utils_bp)
app.register_blueprint(decisiones_bp)
app.register_blueprint(mapas_shp_bp)
app.register_blueprint(areas_bp)
app.register_blueprint(difusion_bp)
app.register_blueprint(mensajeria_bp)
app.register_blueprint(seguimiento_cultivo_bp)
app.register_blueprint(evaluacion_riesgo_bp)
app.register_blueprint(capas_riesgo_bp)
app.register_blueprint(clasificar_cliente_bp)
app.register_blueprint(mapa_calor_siniestros_bp)
app.register_blueprint(siniestros_agricultor_bp)

# ── Seguridad: candado global ───────────────────────────────────────────────
# Antes ~70 rutas (exportar clientes, enviar mensajes, descargar OUTPUT, etc.)
# respondían sin sesión. Ahora TODO exige login, salvo lo listado abajo.
# Para llamadas máquina-a-máquina (n8n) se acepta el header X-API-Key si la
# variable de entorno API_KEY está definida.
import hmac
from flask import jsonify, redirect, url_for
from flask_login import current_user

_RUTAS_PUBLICAS = {
    'auth.login', 'utils.health', 'static',
    # Formulario de siniestro: lo llena el agricultor desde un link, sin cuenta.
    'siniestros_agricultor.formulario', 'siniestros_agricultor.guardar',
}
_API_KEY = os.getenv('API_KEY', '')

app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_UPLOAD_MB', '25')) * 1024 * 1024
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
if os.getenv('COOKIE_SECURE', '').lower() in ('1', 'true', 'yes'):
    app.config['SESSION_COOKIE_SECURE'] = True


# Subdominios dedicados en producción (EasyPanel/DNS debe apuntarlos al mismo
# contenedor — esto solo decide a qué página van cuando entran por la raíz "/").
_SUBDOMINIO_DESTINO = {
    'reportar-siniestros-lapositiva.intismart.com': '/siniestro/reportar',
    'inspector-siniestros-lapositiva.intismart.com': '/evaluacion-riesgo/',
}


@app.before_request
def redirigir_por_subdominio():
    host = request.host.split(':')[0].lower()
    destino = _SUBDOMINIO_DESTINO.get(host)
    if destino and request.path == '/':
        return redirect(destino)
    return None


@app.before_request
def exigir_login():
    if request.endpoint in _RUTAS_PUBLICAS or request.method == 'OPTIONS':
        return None
    if current_user.is_authenticated:
        # Perfil Inspector: solo puede ver Evaluación de Riesgo (y su cola de
        # siniestros, que vive en el mismo blueprint) — todo lo demás, afuera.
        if getattr(current_user, 'role', 'admin') == 'inspector':
            endpoint = request.endpoint or ''
            permitido = (
                endpoint.startswith('evaluacion_riesgo.')
                or endpoint in ('auth.logout', 'static')
            )
            if not permitido:
                if request.path.startswith('/api/'):
                    return jsonify({'status': 'error', 'message': 'No autorizado para este perfil'}), 403
                return redirect(url_for('evaluacion_riesgo.index'))
        return None
    clave = request.headers.get('X-API-Key', '')
    if _API_KEY and clave and hmac.compare_digest(clave, _API_KEY):
        return None
    if request.path.startswith('/api/') or request.path in ('/procesar-aviso', '/enviar'):
        return jsonify({'status': 'error', 'message': 'No autorizado'}), 401
    return redirect(url_for('auth.login', next=request.path))


@app.after_request
def cabeceras_seguridad(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'same-origin')
    return response

# ── Sin caché en todas las rutas /api/ ──────────────────────────────────────
@app.after_request
def no_cache_api(response):
    """Deshabilita el caché del navegador para todas las respuestas /api/."""
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

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

@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200
# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

def _precargar_capas_riesgo():
    """Las capas de riesgo (inundación, mov. masa, etc.) se cachean en memoria
    recién cuando alguien las pide por primera vez — para Inundación eso son
    ~24s de lectura de un geojson de 26MB (ver feedback_dissolve_es_el_cuello_de_botella).
    Sin esto, le toca ese costo al primer usuario real (ej. el Inspector abriendo
    el primer caso) en vez de pagarse una sola vez al arrancar el server."""
    try:
        from routes.evaluacion_riesgo import _cargar_capa_preview, EVENTOS
        from routes.capas_riesgo import CAPAS_DISPONIBLES, _cargar_capa_preview_gdf, _cargar_capa_preview_gdf_nacional

        nombres = {'rio'}
        for ev in EVENTOS.values():
            c = ev['capa']
            nombres.update(c if isinstance(c, list) else [c])
        nombres.discard(None)
        nombres.discard('')

        for n in nombres:
            _cargar_capa_preview(n)       # cache propio de evaluacion_riesgo.py
        for n in CAPAS_DISPONIBLES:
            _cargar_capa_preview_gdf(n)        # cache propio de capas_riesgo.py (Mapa Clientes/clasificar-excel)
            _cargar_capa_preview_gdf_nacional(n)  # cache para /geometria?depto= (Seguro Comercial)
        logger.info('Capas de riesgo precargadas en memoria: %s', sorted(nombres))
    except Exception as e:
        logger.warning('No se pudieron precargar las capas de riesgo: %s', str(e))


if __name__ == '__main__':
    # Crear directorios si no existen
    (BASE_DIR / "TEMP").mkdir(exist_ok=True)
    (BASE_DIR / "OUTPUT").mkdir(exist_ok=True)

    # logger.info("🚀 Iniciando servidor Flask - Avisos SENAMHI")
    # logger.info(f"📁 Directorio base: {BASE_DIR}")
    # logger.info(f"📊 Directorio de salida: {OUTPUT_DIR}")
    # logger.info(f"🌐 Dominio: {DOMAIN}")

    threading.Thread(target=_precargar_capas_riesgo, daemon=True).start()

    # Ejecutar servidor
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        use_reloader=False,
        threaded=True
    )
