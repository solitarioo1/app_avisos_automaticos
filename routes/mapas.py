"""
Rutas de Mapas - Vistas y APIs para galería de mapas meteorológicos
"""
from flask import Blueprint, render_template, request, send_from_directory, jsonify
from pathlib import Path
import os
import logging
from datetime import datetime

# Configuración
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / 'OUTPUT'
logger = logging.getLogger(__name__)

# Crear blueprint
mapas_bp = Blueprint('mapas', __name__, url_prefix='')


def obtener_lista_mapas(aviso_filtro=None):
    """Obtener lista de mapas para galería"""
    mapas = []
    
    if OUTPUT_DIR.exists():
        avisos_dirs = [d for d in OUTPUT_DIR.iterdir() 
                      if d.is_dir() and d.name.startswith('aviso_')]
        
        if aviso_filtro:
            avisos_dirs = [d for d in avisos_dirs if d.name == f'aviso_{aviso_filtro}']
        
        avisos_dirs = sorted(avisos_dirs, key=lambda x: x.stat().st_mtime, reverse=True)
        
        for aviso_dir in avisos_dirs:
            numero_aviso = aviso_dir.name.replace('aviso_', '')
            webp_files = [f for f in aviso_dir.iterdir() if f.suffix == '.webp']
            
            for webp_file in webp_files:
                url_local = f"/mapas/imagen/{numero_aviso}/{webp_file.name}"
                
                mapas.append({
                    'id': f"{numero_aviso}_{webp_file.stem}",
                    'nombre': f"{webp_file.stem}.webp",
                    'numero_aviso': numero_aviso,
                    'departamento': webp_file.stem,
                    'url': url_local,
                    'fecha': datetime.fromtimestamp(aviso_dir.stat().st_mtime).strftime('%d/%m/%Y')
                })
    
    return mapas


@mapas_bp.route('/mapas', methods=['GET'])
def mapas():
    """Galería de mapas"""
    try:
        aviso_filtro = request.args.get('aviso')
        mapas_lista = obtener_lista_mapas(aviso_filtro)
        return render_template('mapas.html', mapas=mapas_lista)
    except Exception as e:
        logger.error(f"Error en página mapas: {str(e)}")
        return render_template('mapas.html', mapas=[])


@mapas_bp.route('/mapas/imagen/<int:numero>/<filename>')
def servir_mapa(numero, filename):
    """Sirve imágenes de mapas"""
    try:
        directorio = OUTPUT_DIR / f'aviso_{numero}'
        return send_from_directory(directorio, filename)
    except Exception as e:
        logger.error(f"Error sirviendo imagen: {str(e)}")
        return "Archivo no encontrado", 404


@mapas_bp.route('/api/mapas/aviso/<int:numero>', methods=['GET'])
def api_mapas_por_aviso(numero):
    """API para obtener lista de mapas de un aviso"""
    try:
        output_path = OUTPUT_DIR / f'aviso_{numero}'
        mapas = []
        
        if output_path.exists():
            for img_file in output_path.glob('*.*'):
                if img_file.suffix.lower() in ['.webp', '.png']:
                    depto = img_file.stem
                    mapas.append({
                        'nombre': depto,
                        'archivo': img_file.name,
                        'url': f'/mapas/imagen/{numero}/{img_file.name}',
                        'ruta': str(img_file)
                    })
        
        return jsonify({
            'success': True,
            'aviso': numero,
            'mapas': mapas,
            'cantidad': len(mapas)
        }), 200
        
    except Exception as e:
        logger.error(f"Error obteniendo mapas de aviso {numero}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
