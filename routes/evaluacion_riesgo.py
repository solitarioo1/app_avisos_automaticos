"""
routes/evaluacion_riesgo.py - Verificación de reclamos por triple cruce:
capa de riesgo climático + aviso SENAMHI + estación meteorológica más cercana.

El umbral NO lo pone el usuario: se calcula un percentil climatológico
(P90/P10 o P95/P5, según severidad elegida) de la propia estación, por mes
calendario, contra el histórico de registros_meteorologicos — método
estándar para extremos climáticos (ej. TX90p/TN10p de ETCCDI).

Alcance actual (30 ago 2026): la ubicación se resuelve para cualquier punto
del Perú (reverse-geocode vía DELIMITACIONES/DISTRITOS/DISTRITOS.shp), pero
el percentil de estación solo va a tener datos reales cerca de Piura, que es
el único departamento con estaciones scrapeadas hasta ahora (ver
[[estaciones-senamhi-scraping]]).
"""
import logging
from datetime import date, datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import geopandas as gpd
import pandas as pd
import psycopg2.extras
from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required
from PIL import ExifTags, Image
from shapely.geometry import Point

from CONFIG.db import get_connection
from routes.capas_riesgo import ARCHIVO_PREVIEW, CAPAS_DISPONIBLES, CLIP_DIR, _COLOR_NIVEL_ESTANDAR, _nivel_estandar

logger = logging.getLogger(__name__)
evaluacion_riesgo_bp = Blueprint('evaluacion_riesgo', __name__, url_prefix='/evaluacion-riesgo')

BASE_DIR = Path(__file__).parent.parent
DISTRITOS_SHP = BASE_DIR / 'DELIMITACIONES' / 'DISTRITOS' / 'DISTRITOS.shp'

MESES = ['', 'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

# Tipo de evento -> capa de riesgo a cruzar + variable de estación + cola del
# percentil ('superior' = evento extremo por valor ALTO, ej. viento/calor;
# 'inferior' = evento extremo por valor BAJO, ej. heladas/sequía).
EVENTOS = {
    'helada':     {'label': 'Helada',              'capa': 'helada',    'variable': 'temp_min',      'cola': 'inferior', 'unidad': '°C',   'acumulado_mensual': False},
    'friaje':     {'label': 'Friaje',               'capa': 'friaje',    'variable': 'temp_min',      'cola': 'inferior', 'unidad': '°C',   'acumulado_mensual': False},
    'sequia':     {'label': 'Sequía',               'capa': 'sequia',    'variable': 'precipitacion', 'cola': 'inferior', 'unidad': 'mm',   'acumulado_mensual': True},
    'viento':     {'label': 'Viento Fuerte',        'capa': 'viento',    'variable': 'vel_viento',    'cola': 'superior', 'unidad': 'km/h', 'acumulado_mensual': False},
    'incendios':  {'label': 'Incendios Forestales', 'capa': 'incendios', 'variable': 'temp_max',      'cola': 'superior', 'unidad': '°C',   'acumulado_mensual': False},
    'inundacion': {'label': 'Lluvias / Inundación', 'capa': 'inundacion', 'variable': 'precipitacion', 'cola': 'superior', 'unidad': 'mm',   'acumulado_mensual': False},
}

# Las estaciones AUTOMATICA/EMA registran por hora (hasta 24 filas/día); las
# CONVENCIONAL registran 3 veces al día (07h/13h/19h). Para que "un día" sea
# un solo punto en la serie/percentil/promedio hay que agregar por fecha con
# la función correcta según la variable (nunca promediar/sumar filas crudas).
_AGREGACION = {'temp_min': 'MIN', 'temp_max': 'MAX', 'vel_viento': 'MAX', 'precipitacion': 'SUM'}

# Rango físico plausible por variable (mismos límites que scraping/scrape_departamento.py
# ::num()). Filtro DEFENSIVO en cada consulta: aunque el scraper ya valida al insertar,
# un dato corrupto que se haya colado a la BD (ej. el -999 de "sin dato" de SENAMHI que
# apareció en 148 filas cargadas antes de esa validación) no debe arruinar un percentil
# ni un reporte de reclamo — nunca confiar ciegamente en que la BD ya está limpia.
_RANGO_VALIDO = {
    'temp_min': (-30, 60), 'temp_max': (-30, 60),
    'vel_viento': (0, 150), 'precipitacion': (0, 999),
}


def _filtro_rango(variable):
    minimo, maximo = _RANGO_VALIDO[variable]
    return f"AND {variable} BETWEEN {minimo} AND {maximo}"

_capa_cache = {}  # nombre -> GeoDataFrame de preview, cacheado en memoria tras la primera consulta
_distritos_gdf = None


def _cargar_distritos():
    global _distritos_gdf
    if _distritos_gdf is None:
        _distritos_gdf = gpd.read_file(DISTRITOS_SHP)
    return _distritos_gdf


def _cargar_capa_preview(nombre):
    if nombre in _capa_cache:
        return _capa_cache[nombre]
    archivo = ARCHIVO_PREVIEW.get(nombre)
    ruta = CLIP_DIR / archivo if archivo else None
    gdf = gpd.read_file(ruta) if ruta and ruta.exists() else None
    _capa_cache[nombre] = gdf
    return gdf


def _haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def _ubicar_punto(lat, lon):
    """Reverse-geocode: punto -> departamento/provincia/distrito."""
    distritos = _cargar_distritos()
    punto = Point(lon, lat)
    match = distritos[distritos.contains(punto)]
    if match.empty:
        return None, None, None
    row = match.iloc[0]
    return row['DEPARTAMEN'], row['PROVINCIA'], row['DISTRITO']


_depto_cache = {}  # nombre departamento -> geometría disuelta (dict geojson), cacheada


def _limite_departamento(nombre):
    """Contorno disuelto de un departamento (para dar contexto local al mapa del
    reporte — evita que el mapa haga zoom a todo el Perú buscando la capa)."""
    if nombre in _depto_cache:
        return _depto_cache[nombre]
    distritos = _cargar_distritos()
    match = distritos[distritos['DEPARTAMEN'] == nombre]
    if match.empty:
        _depto_cache[nombre] = None
        return None
    disuelto = match.dissolve()
    geojson = disuelto[['geometry']].__geo_interface__
    _depto_cache[nombre] = geojson
    return geojson


def _fraccion_percentil(cola, severidad):
    """severidad: 90 o 95. cola 'superior' -> P90/P95; 'inferior' -> P10/P5."""
    return severidad / 100 if cola == 'superior' else (100 - severidad) / 100


def _percentil_mensual(cur, estacion_id, variable, mes, fraccion, acumulado_mensual):
    """Percentil histórico de la estación para ese mes calendario (todos los años)."""
    if acumulado_mensual:
        cur.execute(f"""
            SELECT percentile_cont(%s) WITHIN GROUP (ORDER BY total) AS p
            FROM (
                SELECT EXTRACT(YEAR FROM fecha) AS anio, SUM({variable}) AS total
                FROM registros_meteorologicos
                WHERE estacion_id = %s AND EXTRACT(MONTH FROM fecha) = %s AND {variable} IS NOT NULL
                      {_filtro_rango(variable)}
                GROUP BY anio
            ) t
        """, (fraccion, estacion_id, mes))
    else:
        agg = _AGREGACION[variable]
        cur.execute(f"""
            SELECT percentile_cont(%s) WITHIN GROUP (ORDER BY valor) AS p
            FROM (
                SELECT fecha, {agg}({variable}) AS valor
                FROM registros_meteorologicos
                WHERE estacion_id = %s AND EXTRACT(MONTH FROM fecha) = %s AND {variable} IS NOT NULL
                      {_filtro_rango(variable)}
                GROUP BY fecha
            ) t
        """, (fraccion, estacion_id, mes))
    r = cur.fetchone()
    return float(r['p']) if r and r['p'] is not None else None


def _promedios_mensuales(cur, estacion_id, variable, acumulado_mensual):
    """Serie Ene..Dic: promedio histórico de la estación para la tabla del reporte."""
    if acumulado_mensual:
        cur.execute(f"""
            SELECT mes, AVG(total) AS promedio FROM (
                SELECT EXTRACT(MONTH FROM fecha) AS mes, EXTRACT(YEAR FROM fecha) AS anio,
                       SUM({variable}) AS total
                FROM registros_meteorologicos
                WHERE estacion_id = %s AND {variable} IS NOT NULL {_filtro_rango(variable)}
                GROUP BY mes, anio
            ) t GROUP BY mes ORDER BY mes
        """, (estacion_id,))
    else:
        agg = _AGREGACION[variable]
        cur.execute(f"""
            SELECT mes, AVG(valor) AS promedio FROM (
                SELECT EXTRACT(MONTH FROM fecha) AS mes, fecha, {agg}({variable}) AS valor
                FROM registros_meteorologicos
                WHERE estacion_id = %s AND {variable} IS NOT NULL {_filtro_rango(variable)}
                GROUP BY mes, fecha
            ) t GROUP BY mes ORDER BY mes
        """, (estacion_id,))
    valores = {int(row['mes']): round(float(row['promedio']), 1) for row in cur.fetchall() if row['promedio'] is not None}
    return [{'mes': MESES[m], 'valor': valores.get(m)} for m in range(1, 13)]


def _serie_diaria(cur, estacion_id, variable, anio, mes):
    """Valores día a día de ese mes/año específico (agregados, 1 punto por día),
    para graficar junto al percentil."""
    agg = _AGREGACION[variable]
    cur.execute(f"""
        SELECT EXTRACT(DAY FROM fecha)::int AS dia, {agg}({variable}) AS valor
        FROM registros_meteorologicos
        WHERE estacion_id = %s AND EXTRACT(YEAR FROM fecha) = %s AND EXTRACT(MONTH FROM fecha) = %s
              AND {variable} IS NOT NULL {_filtro_rango(variable)}
        GROUP BY dia ORDER BY dia
    """, (estacion_id, anio, mes))
    return [{'dia': row['dia'], 'valor': float(row['valor'])} for row in cur.fetchall()]


def _capa_en_punto(evento, punto):
    nombre_capa = evento['capa']
    capa_gdf = _cargar_capa_preview(nombre_capa)
    capa_info = CAPAS_DISPONIBLES.get(nombre_capa, {})
    en_capa, nivel_capa = False, None
    if capa_gdf is not None and not capa_gdf.empty:
        campo_cat = capa_info.get('campo_categoria')
        match_capa = capa_gdf[capa_gdf.contains(punto)]
        if not match_capa.empty:
            en_capa = True
            valor_crudo = match_capa.iloc[0][campo_cat] if campo_cat else None
            nivel_capa = _nivel_estandar(nombre_capa, valor_crudo)  # Muy Alto/Alto/Medio/Bajo
    return {
        'nombre': nombre_capa, 'label': capa_info.get('label', nombre_capa),
        'disponible': capa_gdf is not None,
        'en_capa': en_capa, 'nivel': nivel_capa,
        'color': _COLOR_NIVEL_ESTANDAR.get(nivel_capa) if nivel_capa else None,
    }


def _aviso_para(departamento, fecha):
    if not departamento:
        return None
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT a.numero_aviso, a.titulo, a.nivel, a.color, a.fecha_inicio, a.fecha_fin
        FROM avisos_completos a
        JOIN aviso_zonas_afectadas z ON z.numero_aviso = a.numero_aviso
        WHERE z.departamento ILIKE %s
          AND a.fecha_inicio <= %s AND a.fecha_fin >= %s
        ORDER BY a.fecha_inicio DESC
        LIMIT 1
    """, (departamento, fecha + timedelta(days=5), fecha - timedelta(days=2)))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        return None
    return {
        'numero_aviso': row['numero_aviso'], 'titulo': row['titulo'],
        'nivel': row['nivel'], 'color': row['color'],
        'fecha_inicio': row['fecha_inicio'].isoformat() if row['fecha_inicio'] else None,
        'fecha_fin': row['fecha_fin'].isoformat() if row['fecha_fin'] else None,
    }


def _estacion_mas_cercana_con_dato(cur, departamento, lat, lon, fecha, variable, acumulado_mensual):
    """Ordena estaciones del departamento por distancia y devuelve la primera con dato
    utilizable (valor puntual +-2 días, o total del mes si es acumulado)."""
    cur.execute("SELECT id, nombre, codigo, latitud, longitud FROM estaciones WHERE departamento ILIKE %s",
                (departamento,))
    estaciones = cur.fetchall()
    for e in estaciones:
        e['_dist'] = _haversine_km(lat, lon, float(e['latitud']), float(e['longitud']))
    estaciones.sort(key=lambda e: e['_dist'])

    for e in estaciones:
        if acumulado_mensual:
            cur.execute(f"""
                SELECT COALESCE(SUM({variable}), 0) AS total, COUNT(DISTINCT fecha) AS n
                FROM registros_meteorologicos
                WHERE estacion_id = %s AND EXTRACT(YEAR FROM fecha) = %s AND EXTRACT(MONTH FROM fecha) = %s
                      AND {variable} IS NOT NULL {_filtro_rango(variable)}
            """, (e['id'], fecha.year, fecha.month))
            r = cur.fetchone()
            if r['n'] > 0:
                return e, float(r['total']), None, r['n']
        else:
            # Agrega por día (las estaciones AUTOMATICA registran por hora) y
            # toma el día más cercano a la fecha del evento dentro de la ventana.
            agg = _AGREGACION[variable]
            cur.execute(f"""
                SELECT fecha, {agg}({variable}) AS valor FROM registros_meteorologicos
                WHERE estacion_id = %s AND fecha BETWEEN %s AND %s
                      AND {variable} IS NOT NULL {_filtro_rango(variable)}
                GROUP BY fecha
                ORDER BY ABS(fecha - %s) LIMIT 1
            """, (e['id'], fecha - timedelta(days=2), fecha + timedelta(days=2), fecha))
            r = cur.fetchone()
            if r:
                return e, float(r['valor']), r['fecha'], None
    return None, None, None, None


def _verificar_punto(evento_id, fecha, lat, lon, severidad, con_detalle_meteo=False):
    """Núcleo del triple cruce, reutilizado por /api/verificar (1 punto, con
    detalle meteorológico completo) y /api/verificar-lote (muchas filas, sin
    detalle para no sobrecargar la respuesta)."""
    evento = EVENTOS.get(evento_id)
    if not evento:
        return {'error': f'Evento "{evento_id}" no reconocido'}

    punto = Point(lon, lat)
    departamento, provincia, distrito = _ubicar_punto(lat, lon)

    resultado = {
        'evento': evento['label'], 'evento_id': evento_id, 'fecha': fecha.isoformat(), 'lat': lat, 'lon': lon,
        'departamento': departamento, 'provincia': provincia, 'distrito': distrito,
        'unidad': evento['unidad'], 'cola': evento['cola'], 'severidad': severidad,
    }

    resultado['capa'] = _capa_en_punto(evento, punto)
    resultado['aviso'] = _aviso_para(departamento, fecha)

    estacion_resultado = None
    if departamento:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        variable = evento['variable']
        e, valor, fecha_dato, dias_con_dato = _estacion_mas_cercana_con_dato(
            cur, departamento, lat, lon, fecha, variable, evento['acumulado_mensual'])

        if e is not None:
            fraccion = _fraccion_percentil(evento['cola'], severidad)
            p_valor = _percentil_mensual(cur, e['id'], variable, fecha.month, fraccion, evento['acumulado_mensual'])
            supera = None
            if p_valor is not None:
                supera = (valor <= p_valor) if evento['cola'] == 'inferior' else (valor >= p_valor)

            estacion_resultado = {
                'estacion': e['nombre'], 'codigo': e['codigo'], 'distancia_km': round(e['_dist'], 1),
                'lat': float(e['latitud']), 'lon': float(e['longitud']),
                'variable': variable,
                'valor': round(valor, 1),
                'fecha_dato': fecha_dato.isoformat() if fecha_dato else None,
                'dias_con_dato': dias_con_dato,
                'percentil': int(severidad if evento['cola'] == 'superior' else 100 - severidad),
                'percentil_valor': round(p_valor, 1) if p_valor is not None else None,
                'supera_percentil': supera,
            }

            if con_detalle_meteo:
                estacion_resultado['promedios_mensuales'] = _promedios_mensuales(
                    cur, e['id'], variable, evento['acumulado_mensual'])
                estacion_resultado['serie_diaria'] = _serie_diaria(cur, e['id'], variable, fecha.year, fecha.month)
                estacion_resultado['dia_evento'] = fecha.day

        cur.close(); conn.close()
    resultado['estacion'] = estacion_resultado

    señales = [resultado['capa']['en_capa'], resultado['aviso'] is not None,
               bool(estacion_resultado and estacion_resultado['supera_percentil'])]
    resultado['señales_positivas'] = sum(señales)
    resultado['veredicto'] = resultado['señales_positivas'] >= 2

    return resultado


@evaluacion_riesgo_bp.route('/', methods=['GET'])
@login_required
def index():
    eventos = [{'id': k, **v} for k, v in EVENTOS.items()]
    return render_template('evaluacion_riesgo.html', eventos=eventos)


def _exif_gps_a_decimal(gps_info):
    def _a_grados(valor):
        d, m, s = valor
        return float(d) + float(m) / 60 + float(s) / 3600

    lat = _a_grados(gps_info['GPSLatitude'])
    if gps_info.get('GPSLatitudeRef') == 'S':
        lat = -lat
    lon = _a_grados(gps_info['GPSLongitude'])
    if gps_info.get('GPSLongitudeRef') == 'W':
        lon = -lon
    return lat, lon


@evaluacion_riesgo_bp.route('/api/extraer-foto', methods=['POST'])
@login_required
def api_extraer_foto():
    """Lee EXIF de una foto subida (GPS + fecha de captura) para precargar el formulario.
    El tipo de evento nunca se infiere de la foto — el usuario siempre lo elige."""
    archivo = request.files.get('foto')
    if not archivo:
        return jsonify({'error': 'No se recibió ninguna foto'}), 400

    try:
        img = Image.open(archivo.stream)
        exif_raw = img._getexif() or {}
    except Exception as e:
        logger.error("Error leyendo EXIF: %s", str(e))
        return jsonify({'error': 'No se pudo leer la imagen'}), 400

    exif = {ExifTags.TAGS.get(k, k): v for k, v in exif_raw.items()}
    resultado = {'lat': None, 'lon': None, 'fecha': None}

    gps_raw = exif.get('GPSInfo')
    if gps_raw:
        gps = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_raw.items()}
        try:
            lat, lon = _exif_gps_a_decimal(gps)
            resultado['lat'] = round(lat, 6)
            resultado['lon'] = round(lon, 6)
        except (KeyError, TypeError, ZeroDivisionError):
            pass

    fecha_raw = exif.get('DateTimeOriginal') or exif.get('DateTime')
    if fecha_raw:
        try:
            resultado['fecha'] = datetime.strptime(fecha_raw, '%Y:%m:%d %H:%M:%S').date().isoformat()
        except ValueError:
            pass

    resultado['tiene_gps'] = resultado['lat'] is not None
    resultado['tiene_fecha'] = resultado['fecha'] is not None
    return jsonify(resultado)


@evaluacion_riesgo_bp.route('/api/ubicacion', methods=['GET'])
@login_required
def api_ubicacion():
    """Reverse-geocode rápido para previsualizar departamento/provincia/distrito al mover el punto."""
    try:
        lat = float(request.args['lat'])
        lon = float(request.args['lon'])
    except (KeyError, ValueError):
        return jsonify({'error': 'lat/lon inválidos'}), 400

    departamento, provincia, distrito = _ubicar_punto(lat, lon)
    return jsonify({'departamento': departamento, 'provincia': provincia, 'distrito': distrito})


@evaluacion_riesgo_bp.route('/api/departamento-geojson', methods=['GET'])
@login_required
def api_departamento_geojson():
    """Contorno del departamento (contexto local para el mapa de Gestión de Riesgo)."""
    nombre = request.args.get('nombre', '').strip().upper()
    if not nombre:
        return jsonify({'error': 'Falta el parámetro nombre'}), 400
    geojson = _limite_departamento(nombre)
    if geojson is None:
        return jsonify({'error': f'Departamento "{nombre}" no encontrado'}), 404
    return jsonify(geojson)


@evaluacion_riesgo_bp.route('/api/estaciones', methods=['GET'])
@login_required
def api_estaciones():
    """Todas las estaciones meteorológicas registradas a nivel nacional, para
    pintarlas de entrada en el mapa. tiene_datos distingue las ~46 de Piura
    (con histórico real scrapeado) del resto (coordenada mapeada, sin datos aún)."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT e.id, e.nombre, e.codigo, e.departamento, e.latitud, e.longitud,
               EXISTS(SELECT 1 FROM registros_meteorologicos r WHERE r.estacion_id = e.id) AS tiene_datos
        FROM estaciones e
        WHERE e.latitud IS NOT NULL AND e.longitud IS NOT NULL
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()

    features = [{
        'type': 'Feature',
        'geometry': {'type': 'Point', 'coordinates': [float(r['longitud']), float(r['latitud'])]},
        'properties': {
            'id': r['id'], 'nombre': r['nombre'], 'codigo': r['codigo'],
            'departamento': r['departamento'], 'tiene_datos': bool(r['tiene_datos']),
        }
    } for r in rows]
    return jsonify({'type': 'FeatureCollection', 'features': features, 'total': len(features)})


@evaluacion_riesgo_bp.route('/api/verificar', methods=['POST'])
@login_required
def api_verificar():
    """Triple cruce para UN punto, con detalle meteorológico completo (tabla
    mensual + serie diaria) para armar el reporte."""
    data = request.get_json(force=True, silent=True) or {}
    try:
        evento_id = data['evento']
        fecha = date.fromisoformat(data['fecha'])
        lat = float(data['lat'])
        lon = float(data['lon'])
        severidad = int(data.get('severidad', 90))
    except (KeyError, ValueError, TypeError):
        return jsonify({'error': 'Faltan datos o son inválidos (evento, fecha, lat, lon)'}), 400

    if evento_id not in EVENTOS:
        return jsonify({'error': f'Evento "{evento_id}" no reconocido'}), 400
    if severidad not in (90, 95):
        severidad = 90

    resultado = _verificar_punto(evento_id, fecha, lat, lon, severidad, con_detalle_meteo=True)
    if 'error' in resultado:
        return jsonify(resultado), 400
    return jsonify(resultado)


_COLS_FECHA = ['fecha', 'fecha_evento', 'date']
_COLS_EVENTO = ['evento', 'tipo_evento', 'tipo']
_COLS_LAT = ['lat', 'latitud', 'latitude']
_COLS_LON = ['lon', 'lng', 'longitud', 'longitude']
_COLS_ID = ['id', 'referencia', 'codigo', 'reclamo', 'cliente']


def _detectar_columna(columnas_lower, candidatos):
    for c in candidatos:
        if c in columnas_lower:
            return columnas_lower[c]
    return None


@evaluacion_riesgo_bp.route('/api/verificar-lote', methods=['POST'])
@login_required
def api_verificar_lote():
    """Verifica muchos reclamos a la vez desde un Excel (columnas: fecha, evento,
    lat/latitud, lon/longitud, y opcionalmente id/referencia). Sin detalle
    meteorológico por fila (solo el resumen) para no sobrecargar la respuesta."""
    archivo = request.files.get('excel')
    if not archivo:
        return jsonify({'error': 'No se recibió ningún archivo'}), 400

    try:
        df = pd.read_excel(archivo)
    except Exception as e:
        logger.error("Error leyendo Excel: %s", str(e))
        return jsonify({'error': 'No se pudo leer el Excel (¿formato .xlsx válido?)'}), 400

    columnas_lower = {str(c).strip().lower(): c for c in df.columns}
    col_fecha = _detectar_columna(columnas_lower, _COLS_FECHA)
    col_evento = _detectar_columna(columnas_lower, _COLS_EVENTO)
    col_lat = _detectar_columna(columnas_lower, _COLS_LAT)
    col_lon = _detectar_columna(columnas_lower, _COLS_LON)
    col_id = _detectar_columna(columnas_lower, _COLS_ID)

    faltantes = [n for n, c in [('fecha', col_fecha), ('evento', col_evento), ('lat', col_lat), ('lon', col_lon)] if not c]
    if faltantes:
        return jsonify({'error': f'Al Excel le faltan columnas: {", ".join(faltantes)}. '
                                  f'Encabezados esperados: fecha, evento, lat/latitud, lon/longitud.'}), 400

    eventos_validos = {k: k for k in EVENTOS}
    eventos_validos.update({v['label'].lower(): k for k, v in EVENTOS.items()})

    resultados = []
    for i, row in df.iterrows():
        referencia = str(row[col_id]) if col_id and pd.notna(row.get(col_id)) else f'Fila {i + 2}'
        try:
            fecha_val = row[col_fecha]
            fecha = fecha_val.date() if hasattr(fecha_val, 'date') else date.fromisoformat(str(fecha_val)[:10])
            evento_raw = str(row[col_evento]).strip().lower()
            evento_id = eventos_validos.get(evento_raw)
            lat = float(row[col_lat])
            lon = float(row[col_lon])
            if not evento_id:
                raise ValueError(f'evento "{row[col_evento]}" no reconocido')

            r = _verificar_punto(evento_id, fecha, lat, lon, 90, con_detalle_meteo=False)
            r['referencia'] = referencia
            resultados.append(r)
        except Exception as e:
            resultados.append({'referencia': referencia, 'error': str(e)})

    return jsonify({'total': len(resultados), 'resultados': resultados})
