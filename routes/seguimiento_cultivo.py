"""
routes/seguimiento_cultivo.py - Identificación de cultivo por coordenada + fecha

Estructura visual (esqueleto): el usuario ingresa coordenada + fecha, el mapa
hace zoom a la zona, y se muestra la respuesta sí/no de si se sembró el
cultivo consultado ahí.

El modelo de clasificación (Sentinel-1/2 + Random Forest, entrenado con las
zonas paperas georreferenciadas) todavía no está entrenado — esta ruta define
la estructura y el endpoint de consulta, pero responde con un estado
"pendiente" hasta que el modelo esté listo.
"""
import glob
import json
import unicodedata
from pathlib import Path

import geopandas as gpd
from flask import Blueprint, render_template, request, jsonify, Response
from flask_login import login_required

seguimiento_cultivo_bp = Blueprint('seguimiento_cultivo', __name__, url_prefix='/seguimiento-cultivo')

BASE_DIR = Path(__file__).parent.parent
CAPAS_DIR = BASE_DIR / 'CAPAS'
CACHE_DIR = BASE_DIR / 'CONFIG' / 'geojson_cache'
DISTRITOS_SHP = BASE_DIR / 'DELIMITACIONES' / 'DISTRITOS' / 'DISTRITOS.shp'
PROVINCIAS_SHP = BASE_DIR / 'DELIMITACIONES' / 'PROVINCIAS' / 'PROVINCIAS.shp'
DEPARTAMENTOS_SHP = BASE_DIR / 'DELIMITACIONES' / 'DEPARTAMENTOS' / 'DEPARTAMENTOS.shp'

_distritos_gdf_cache = None
_provincias_gdf_cache = None
_departamentos_gdf_cache = None

# Capas disponibles y de qué carpeta salen. "por_departamento": True significa
# que el archivo ya viene pre-dividido por departamento (así evitamos cargar
# los ~700MB combinados de golpe — solo se lee el archivo del depto pedido).
CAPAS_CONFIG = {
    'zona_agricola':      {'carpeta': 'CAPA_SUPERFICIE_AGRICOLA', 'por_departamento': True},
    'sector_estadistico': {'carpeta': 'CAPA_SECTORES_ESTADISTICOS', 'por_departamento': True},
    'mango':              {'carpeta': 'CAPA_MANGO', 'por_departamento': True},
    'arroz':              {'carpeta': 'CAPA_ARROZ', 'por_departamento': False, 'archivo': 'Arroz_PERU.shp'},
}

_ubicaciones_cache = None


def _normalizar(texto):
    """Mayúsculas, sin acentos, sin espacios extra — para comparar nombres de forma robusta."""
    texto = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode('ascii')
    return texto.strip().upper()


def _cargar_ubicaciones():
    """Departamento -> Provincia -> [Distritos], sacado de DELIMITACIONES/DISTRITOS.shp."""
    global _ubicaciones_cache
    if _ubicaciones_cache is not None:
        return _ubicaciones_cache

    gdf = gpd.read_file(DISTRITOS_SHP)
    estructura = {}
    vistos = set()
    for _, row in gdf.iterrows():
        dep, prov, dist = row['DEPARTAMEN'], row['PROVINCIA'], row['DISTRITO']
        clave = (dep, prov, dist)
        if clave in vistos:
            continue
        vistos.add(clave)
        estructura.setdefault(dep, {}).setdefault(prov, []).append(dist)

    for dep in estructura:
        for prov in estructura[dep]:
            estructura[dep][prov].sort()

    _ubicaciones_cache = estructura
    return estructura


def _buscar_archivo_por_departamento(carpeta, departamento):
    """Busca, dentro de la carpeta de la capa, el archivo cuyo nombre contenga el departamento."""
    dep_norm = _normalizar(departamento).replace(' ', '')
    for ext in ('.shp', '.gpkg'):
        for archivo in glob.glob(str(CAPAS_DIR / carpeta / f'*{ext}')):
            nombre = _normalizar(Path(archivo).stem).replace(' ', '').replace('_', '')
            if dep_norm.replace('_', '') in nombre:
                return archivo
    return None


@seguimiento_cultivo_bp.route('/', methods=['GET'])
@login_required
def index():
    """Página principal: mapa + formulario de consulta por coordenada y fecha."""
    return render_template('seguimiento_cultivo.html')


@seguimiento_cultivo_bp.route('/api/consultar', methods=['POST'])
@login_required
def consultar():
    """
    Consulta si se sembró un cultivo en una coordenada y fecha dadas.

    Body esperado: { "lat": float, "lon": float, "fecha": "YYYY-MM-DD", "cultivo": "papa" }

    El modelo de clasificación todavía no está entrenado, así que por ahora
    responde con estado "pendiente" en vez de un sí/no real.
    """
    data = request.get_json(silent=True) or {}
    lat = data.get('lat')
    lon = data.get('lon')
    fecha = data.get('fecha')
    cultivo = (data.get('cultivo') or 'papa').lower()

    if lat is None or lon is None or not fecha:
        return jsonify({'success': False, 'mensaje': 'Faltan lat, lon o fecha'}), 400

    return jsonify({
        'success': True,
        'estado': 'pendiente',
        'mensaje': 'El modelo de clasificación todavía no está entrenado. '
                   'Esta consulta quedará disponible cuando el entrenamiento '
                   '(Sentinel-1/2 + Random Forest) esté listo.',
        'consulta': {'lat': lat, 'lon': lon, 'fecha': fecha, 'cultivo': cultivo}
    })


def _get_distritos_gdf():
    global _distritos_gdf_cache
    if _distritos_gdf_cache is None:
        gdf = gpd.read_file(DISTRITOS_SHP)
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        _distritos_gdf_cache = gdf
    return _distritos_gdf_cache


def _get_provincias_gdf():
    global _provincias_gdf_cache
    if _provincias_gdf_cache is None:
        gdf = gpd.read_file(PROVINCIAS_SHP)
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        _provincias_gdf_cache = gdf
    return _provincias_gdf_cache


def _get_departamentos_gdf():
    global _departamentos_gdf_cache
    if _departamentos_gdf_cache is None:
        gdf = gpd.read_file(DEPARTAMENTOS_SHP)
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        _departamentos_gdf_cache = gdf
    return _departamentos_gdf_cache


@seguimiento_cultivo_bp.route('/api/extent', methods=['GET'])
@login_required
def extent():
    """
    Límites (bounding box) del departamento/provincia/distrito seleccionado,
    para que el mapa haga zoom automático a esa zona (fitBounds en Leaflet).

    Prioridad: distrito > provincia > departamento (el más específico que venga).
    """
    departamento = request.args.get('departamento', '').strip()
    provincia = request.args.get('provincia', '').strip()
    distrito = request.args.get('distrito', '').strip()

    if not departamento:
        return jsonify({'error': 'falta departamento'}), 400

    try:
        if distrito and provincia:
            gdf = _get_distritos_gdf()
            gdf = gdf[
                gdf['DEPARTAMEN'].apply(lambda x: _normalizar(x) == _normalizar(departamento)) &
                gdf['PROVINCIA'].apply(lambda x: _normalizar(x) == _normalizar(provincia)) &
                gdf['DISTRITO'].apply(lambda x: _normalizar(x) == _normalizar(distrito))
            ]
        elif provincia:
            gdf = _get_provincias_gdf()
            columna_dep = 'DEPARTAMEN' if 'DEPARTAMEN' in gdf.columns else 'NOMBDEP'
            columna_prov = 'PROVINCIA' if 'PROVINCIA' in gdf.columns else 'NOMBPROV'
            gdf = gdf[
                gdf[columna_dep].apply(lambda x: _normalizar(x) == _normalizar(departamento)) &
                gdf[columna_prov].apply(lambda x: _normalizar(x) == _normalizar(provincia))
            ]
        else:
            gdf = _get_departamentos_gdf()
            columna_dep = 'DEPARTAMEN' if 'DEPARTAMEN' in gdf.columns else 'DPTONOM02'
            gdf = gdf[gdf[columna_dep].apply(lambda x: _normalizar(x) == _normalizar(departamento))]

        if gdf.empty:
            return jsonify({'error': 'no se encontró la zona'}), 404

        minx, miny, maxx, maxy = gdf.total_bounds

        gdf_geom = gdf[['geometry']].copy()
        gdf_geom['geometry'] = gdf_geom['geometry'].simplify(0.0003, preserve_topology=True)

        return jsonify({
            'bounds': [[miny, minx], [maxy, maxx]],  # [[sur,oeste],[norte,este]]
            'limite': json.loads(gdf_geom.to_json())
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@seguimiento_cultivo_bp.route('/api/ubicaciones', methods=['GET'])
@login_required
def ubicaciones():
    """Departamento -> Provincia -> [Distritos] para los filtros en cascada."""
    return jsonify(_cargar_ubicaciones())


@seguimiento_cultivo_bp.route('/api/capa/<nombre>', methods=['GET'])
@login_required
def capa(nombre):
    """
    GeoJSON de una capa (zona_agricola, sector_estadistico, mango, arroz),
    filtrado por departamento (?departamento=JUNIN) para no mandar el país
    entero de una — algunas capas pesan cientos de MB completas.
    """
    config = CAPAS_CONFIG.get(nombre)
    if not config:
        return jsonify({'error': f'capa desconocida: {nombre}'}), 404

    departamento = request.args.get('departamento', '').strip()

    # Camino rápido: si ya hay un GeoJSON pre-generado (ver CONFIG/precache_capas.py),
    # lo servimos directo del disco en vez de simplificar el shapefile al vuelo
    # (para capas pesadas como zona_agricola eso tarda 15-30s por departamento).
    if departamento:
        dep_cache = _normalizar(departamento).replace(' ', '_')
        archivo_cache = CACHE_DIR / f"{nombre}_{dep_cache}.geojson"
        if archivo_cache.exists():
            return Response(archivo_cache.read_text(encoding='utf-8'), mimetype='application/json')

    try:
        if config['por_departamento']:
            if not departamento:
                return jsonify({'type': 'FeatureCollection', 'features': []})
            archivo = _buscar_archivo_por_departamento(config['carpeta'], departamento)
            if not archivo:
                # ej. mango solo existe en Cajamarca/Lambayeque/Piura
                return jsonify({'type': 'FeatureCollection', 'features': []})
        else:
            archivo = str(CAPAS_DIR / config['carpeta'] / config['archivo'])

        gdf = gpd.read_file(archivo)

        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        # La capa de arroz no viene pre-dividida (son solo 9 filas, una por depto)
        if departamento and 'NOMBDEP' in gdf.columns:
            gdf = gdf[gdf['NOMBDEP'].apply(lambda x: _normalizar(x) == _normalizar(departamento))]

        # Nos quedamos solo con columnas útiles para el popup/tooltip — reduce
        # el peso del GeoJSON y evita columnas de fecha (Timestamp) que
        # to_json() no sabe serializar.
        columnas_utiles = [c for c in gdf.columns if c in (
            'NOMBDEP', 'NOMBPROV', 'NOMBDIST', 'NOM_SE', 'CATEGORIA', 'USO',
            'AREA_HA', 'AREA_SE', 'CAPITAL',
            'mango_t', 'mango_h', 'mango_r', 'mango_s', 'geometry'
        )]
        gdf = gdf[columnas_utiles]

        # Cinturón de seguridad: cualquier columna de fecha que se haya
        # colado (Timestamp no es serializable por to_json()) se convierte a texto.
        for col in gdf.columns:
            if col != 'geometry' and gdf[col].dtype.kind == 'M':
                gdf[col] = gdf[col].astype(str)

        # Simplifica geometría (tolerancia ~50m) para que el navegador no reciba
        # miles de vértices innecesarios de capas grandes como zona_agricola.
        gdf['geometry'] = gdf['geometry'].simplify(0.0005, preserve_topology=True)

        return Response(gdf.to_json(), mimetype='application/json')

    except Exception as e:
        return jsonify({'error': str(e)}), 500
