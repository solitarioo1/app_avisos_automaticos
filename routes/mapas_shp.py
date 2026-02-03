"""
Rutas de Mapas y SHP - Endpoints para capas geoespaciales
Maneja SHP de avisos y delimitaciones (departamentos, provincias, distritos)
"""
import logging
import sys
from pathlib import Path

import geopandas as gpd
from flask import Blueprint, jsonify

sys.path.insert(0, str(Path(__file__).parent.parent / 'LAYOUT'))
try:
    from utils import seleccionar_dia_critico
except ImportError:
    seleccionar_dia_critico = None

BASE_DIR = Path(__file__).parent.parent
TEMP_DIR = BASE_DIR / 'TEMP'
DELIMITACIONES_DIR = BASE_DIR / 'DELIMITACIONES'

logger = logging.getLogger(__name__)
mapas_shp_bp = Blueprint('mapas_shp', __name__, url_prefix='')


# ============================================================================
# ENDPOINTS - SHP AVISOS
# ============================================================================

@mapas_shp_bp.route('/api/avisos/<int:numero>/shp-geojson', methods=['GET'])
def obtener_shp_geojson(numero):
    """
    Devuelve GeoJSON del SHP coloreado por nivel de riesgo
    Lee del día crítico (mayor área ALTO/MUY_ALTO)
    Colores: Rojo (#FF0000) = Nivel 4, Naranja (#FF8C00) = Nivel 3, Gris = otros
    """
    try:
        temp_base = TEMP_DIR / f'aviso_{numero}'

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
            'Nivel 1': '#90EE90'   # Verde - BAJO
        }

        # Agregar columna de color
        gdf['fill_color'] = gdf['nivel'].map(nivel_color).fillna('#E8E8E8')

        # Retornar features con propiedades para Leaflet
        features = []
        for _, row in gdf.iterrows():
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


# ============================================================================
# ENDPOINTS - DELIMITACIONES
# ============================================================================

@mapas_shp_bp.route('/api/delimitaciones/departamentos', methods=['GET'])
def obtener_departamentos():
    """Devuelve GeoJSON de departamentos del Perú"""
    try:
        shp_path = DELIMITACIONES_DIR / 'DEPARTAMENTOS' / 'DEPARTAMENTOS.shp'
        if not shp_path.exists():
            return jsonify({'error': 'Shapefile no encontrado'}), 404

        gdf = gpd.read_file(str(shp_path))
        logger.info("Columnas SHP departamentos: %s", list(gdf.columns))
        logger.info("CRS original: %s", gdf.crs)
        
        # CONVERTIR A WGS84 (EPSG:4326) para Leaflet
        if gdf.crs and gdf.crs != 'EPSG:4326':
            gdf = gdf.to_crs('EPSG:4326')
            logger.info("CRS convertido a EPSG:4326")
        
        features = []
        for _, row in gdf.iterrows():
            # Buscar nombre en diferentes columnas posibles
            nombre_depto = 'Sin nombre'
            for col in ['DPTONOM02', 'DEPARTAMEN', 'NAME', 'NOMBDEP', 'DEPARTAMENTO']:
                if col in row.index and row[col]:
                    nombre_depto = str(row[col]).upper().strip()
                    break
            
            feature = {
                'type': 'Feature',
                'geometry': row.geometry.__geo_interface__,
                'properties': {
                    'DEPARTAMEN': nombre_depto,  # Estandarizar
                    'nombre': nombre_depto,
                    'tipo': 'departamento'
                }
            }
            features.append(feature)

        logger.info("Departamentos cargados: %d (ej: %s)", len(features), 
                   features[0]['properties']['nombre'] if features else 'N/A')
        
        return jsonify({
            'type': 'FeatureCollection',
            'features': features,
            'total': len(features)
        })

    except (OSError, ValueError) as e:
        logger.error("Error en departamentos: %s", str(e))
        return jsonify({'error': str(e)}), 500


@mapas_shp_bp.route('/api/delimitaciones/provincias', methods=['GET'])
def obtener_provincias():
    """Devuelve GeoJSON de provincias del Perú"""
    try:
        shp_path = DELIMITACIONES_DIR / 'PROVINCIAS' / 'PROVINCIAS.shp'
        if not shp_path.exists():
            return jsonify({'error': 'Shapefile no encontrado'}), 404

        gdf = gpd.read_file(str(shp_path))
        features = []
        for _, row in gdf.iterrows():
            feature = {
                'type': 'Feature',
                'geometry': row.geometry.__geo_interface__,
                'properties': {
                    'PROVINCIA': row.get('PROVINCIA', 'Sin nombre'),
                    'DEPARTAMEN': row.get('DEPARTAMEN', ''),
                    'nombre': row.get('PROVINCIA', 'Sin nombre'),
                    'tipo': 'provincia'
                }
            }
            features.append(feature)

        return jsonify({
            'type': 'FeatureCollection',
            'features': features,
            'total': len(features)
        })

    except (OSError, ValueError) as e:
        logger.error("Error en provincias: %s", str(e))
        return jsonify({'error': str(e)}), 500


@mapas_shp_bp.route('/api/delimitaciones/distritos', methods=['GET'])
def obtener_distritos():
    """Devuelve GeoJSON de distritos del Perú"""
    try:
        shp_path = DELIMITACIONES_DIR / 'DISTRITOS' / 'DISTRITOS.shp'
        if not shp_path.exists():
            return jsonify({'error': 'Shapefile no encontrado'}), 404

        gdf = gpd.read_file(str(shp_path))
        features = []
        for _, row in gdf.iterrows():
            feature = {
                'type': 'Feature',
                'geometry': row.geometry.__geo_interface__,
                'properties': {
                    'DISTRITO': row.get('DISTRITO', 'Sin nombre'),
                    'PROVINCIA': row.get('PROVINCIA', ''),
                    'DEPARTAMEN': row.get('DEPARTAMEN', ''),
                    'nombre': row.get('DISTRITO', 'Sin nombre'),
                    'tipo': 'distrito'
                }
            }
            features.append(feature)

        return jsonify({
            'type': 'FeatureCollection',
            'features': features,
            'total': len(features)
        })

    except (OSError, ValueError) as e:
        logger.error("Error en distritos: %s", str(e))
        return jsonify({'error': str(e)}), 500
