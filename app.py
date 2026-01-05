"""
API Flask para procesamiento automático de avisos SENAMHI
Interfaz HTTP para integración con n8n
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

# Agregar LAYOUT al path para importar procesar_aviso
sys.path.insert(0, str(Path(__file__).parent))

from procesar_aviso import procesar_aviso
from CONFIG.db import obtener_aviso_por_numero

# Inicializar Flask
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# Rutas base (desde .env)
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / os.getenv('OUTPUT_DIR', 'OUTPUT')

@app.route('/health', methods=['GET'])
def health():
    """Endpoint de salud - verifica que la API está funcionando"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    }), 200


@app.route('/procesar-aviso', methods=['POST'])
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
        # Validar JSON
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'JSON body requerido'
            }), 400
        
        # Extraer número de aviso
        numero_aviso = data.get('numero_aviso')
        if not numero_aviso:
            return jsonify({
                'status': 'error',
                'message': 'Campo "numero_aviso" requerido'
            }), 400
        
        # Convertir a entero
        try:
            numero_aviso = int(numero_aviso)
        except (ValueError, TypeError):
            return jsonify({
                'status': 'error',
                'message': f'numero_aviso debe ser un entero, recibido: {numero_aviso}'
            }), 400
        
        # Determinar si obtener desde BD o archivo
        desde_bd = data.get('desde_bd', False)
        json_path = data.get('json_path', None)
        
        if json_path:
            json_path = Path(json_path)
            if not json_path.exists():
                return jsonify({
                    'status': 'error',
                    'message': f'Archivo JSON no encontrado: {json_path}'
                }), 400
        
        # Si se solicita desde BD, verificar que exista
        if desde_bd:
            aviso_bd = obtener_aviso_por_numero(numero_aviso)
            if not aviso_bd:
                return jsonify({
                    'status': 'error',
                    'message': f'Aviso {numero_aviso} no encontrado en base de datos'
                }), 404
        
        logger.info(f"Iniciando procesamiento de aviso {numero_aviso} (desde_bd={desde_bd})")
        
        # Procesar aviso
        resultado = procesar_aviso(numero_aviso, desde_bd)
        
        # Obtener lista de mapas generados
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
        
        return jsonify({
            'status': 'success',
            'numero_aviso': numero_aviso,
            'output_dir': str(output_dir),
            'mapas': sorted(mapas),
            'archivos_adicionales': sorted(archivos_adicionales),
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"Error procesando aviso: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Error al procesar aviso: {str(e)}'
        }), 500


@app.route('/avisos/<int:numero_aviso>', methods=['GET'])
def obtener_aviso(numero_aviso):
    """
    Endpoint para obtener detalles de un aviso ya procesado
    
    Respuesta:
    {
        "numero_aviso": 447,
        "existe": true,
        "output_dir": "/path/to/OUTPUT/aviso_447",
        "mapas": ["departamento1.webp"],
        "archivos_adicionales": ["provincias_afectadas.csv"]
    }
    """
    try:
        output_dir = OUTPUT_DIR / f"aviso_{numero_aviso}"
        
        if not output_dir.exists():
            return jsonify({
                'status': 'not_found',
                'numero_aviso': numero_aviso,
                'existe': False,
                'message': f'Aviso {numero_aviso} no encontrado'
            }), 404
        
        # Listar archivos
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


@app.route('/status', methods=['GET'])
def status():
    """Endpoint para verificar estado general de la API"""
    try:
        # Verificar directorios
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


@app.errorhandler(404)
def not_found(error):
    """Manejador de rutas no encontradas"""
    return jsonify({
        'status': 'error',
        'message': 'Ruta no encontrada'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Manejador de errores internos"""
    logger.error(f"Error interno: {str(error)}")
    return jsonify({
        'status': 'error',
        'message': 'Error interno del servidor'
    }), 500


if __name__ == '__main__':
    # Crear directorios si no existen
    (BASE_DIR / "TEMP").mkdir(exist_ok=True)
    (BASE_DIR / "OUTPUT").mkdir(exist_ok=True)
    
    # Ejecutar con debug en desarrollo
    # Para producción usar gunicorn: gunicorn -w 4 -b 0.0.0.0:5000 app:app
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        threaded=True
    )
