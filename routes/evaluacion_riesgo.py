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
    # Huayco/movimiento de masa: sin estación propia que mida esto, se usa
    # precipitación acumulada como proxy (los huaycos en Perú se disparan por
    # lluvia intensa) — igual criterio que Sequía pero de cola superior.
    'huayco':     {'label': 'Huayco',               'capa': 'mov_masa', 'variable': 'precipitacion', 'cola': 'superior', 'unidad': 'mm',   'acumulado_mensual': True},
    # Inundación cruza 2 capas (pedido explícito, 3 sep 2026): la propia capa
    # de Inundación Y Río/Faja Marginal — la cercanía al río también es señal
    # de riesgo de desborde, no solo estar dentro del polígono de inundación.
    'inundacion': {'label': 'Lluvias / Inundación', 'capa': ['inundacion', 'rio'], 'variable': 'precipitacion', 'cola': 'superior', 'unidad': 'mm', 'acumulado_mensual': False},
    # Sin capa propia (no existe capa de "ola de calor"/estrés térmico en
    # cultivos — reusar "incendios" no tendría lógica, es susceptibilidad a
    # incendio forestal, no calor sobre el cultivo). El veredicto se apoya
    # solo en estación (percentil de temp_max) + aviso SENAMHI, 2 señales
    # en vez de 3 — capa=[] es válido, ver _capas_en_punto.
    'temperatura_alta': {'label': 'Temperatura Alta', 'capa': [], 'variable': 'temp_max', 'cola': 'superior', 'unidad': '°C', 'acumulado_mensual': False},
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


# variable -> (acumulado_mensual, cola para el percentil)
_VARIABLES_GRAFICA = {
    'precipitacion': True,
    'temp_max': False,
    'temp_min': False,
}


def _grafica_estacion(cur, estacion_id, mes):
    """PP/Tmax/Tmin mensual de la estación (promedio histórico Ene-Dic) + P90
    y P95 del mes del evento, para graficar en el detalle del siniestro —
    pedido explícito del inspector, no solo el resumen de 1 variable."""
    out = {}
    for variable, acumulado in _VARIABLES_GRAFICA.items():
        out[variable] = {
            'mensual': _promedios_mensuales(cur, estacion_id, variable, acumulado),
            'p90': _percentil_mensual(cur, estacion_id, variable, mes, 0.90, acumulado),
            'p95': _percentil_mensual(cur, estacion_id, variable, mes, 0.95, acumulado),
        }
    return out


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


def _capas_en_punto(evento, punto):
    """Devuelve una lista de resultados de capa. La mayoría de eventos cruzan
    una sola (evento['capa'] es str); Inundación cruza 2 (evento['capa'] es
    list: Inundación + Río) — ver comentario en EVENTOS."""
    nombres = evento['capa'] if isinstance(evento['capa'], list) else [evento['capa']]
    resultados = []
    for nombre_capa in nombres:
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
            elif nombre_capa == 'rio':
                # El archivo solo trae 3 bandas explícitas (Muy Alto/Alto/Medio,
                # hasta 1km — si se dibujara "Bajo" como polígono saldría
                # gigante/pesado). Todo punto que NO cae en esas 3 bandas es
                # Bajo por definición (sin importar si está a 3km o 50km) —
                # para verificar un reclamo de seguro todo punto necesita
                # veredicto, no puede quedar "sin clasificar".
                en_capa = True
                nivel_capa = 'Bajo'
        resultados.append({
            'nombre': nombre_capa, 'label': capa_info.get('label', nombre_capa),
            'disponible': capa_gdf is not None,
            'en_capa': en_capa, 'nivel': nivel_capa,
            'color': _COLOR_NIVEL_ESTANDAR.get(nivel_capa) if nivel_capa else None,
        })
    return resultados


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
    """Ordena estaciones por distancia REAL al punto (sin filtrar por departamento
    — la estación físicamente más cercana puede estar del otro lado de un límite
    departamental; filtrar por 'departamento' del punto excluía esas y terminaba
    devolviendo una estación más lejana del mismo departamento, dato incorrecto)
    y devuelve la más cercana con dato utilizable (valor puntual +-2 días, o total
    del mes si es acumulado). `departamento` queda sin usar, se mantiene en la
    firma porque _verificar_punto ya lo tiene calculado.

    UNA sola consulta cubriendo TODAS las estaciones (no una por estación) —
    con la BD remota en el VPS, iterar estación por estación (como antes)
    significaba un viaje de ida y vuelta por cada una; si el punto cae lejos
    de Piura (única zona con datos reales hoy) terminaba recorriéndolas casi
    todas y tardaba 1-3 minutos por caso. Acá se trae el dato de todas de un
    tiro y se elige en Python."""
    cur.execute("SELECT id, nombre, codigo, latitud, longitud FROM estaciones")
    estaciones = cur.fetchall()
    for e in estaciones:
        e['_dist'] = _haversine_km(lat, lon, float(e['latitud']), float(e['longitud']))
    ids_estaciones = [e['id'] for e in estaciones]
    if not ids_estaciones:
        return None, None, None, None

    if acumulado_mensual:
        cur.execute(f"""
            SELECT estacion_id, COALESCE(SUM({variable}), 0) AS total, COUNT(DISTINCT fecha) AS n
            FROM registros_meteorologicos
            WHERE estacion_id = ANY(%s) AND EXTRACT(YEAR FROM fecha) = %s AND EXTRACT(MONTH FROM fecha) = %s
                  AND {variable} IS NOT NULL {_filtro_rango(variable)}
            GROUP BY estacion_id
            HAVING COUNT(DISTINCT fecha) > 0
        """, (ids_estaciones, fecha.year, fecha.month))
        por_estacion = {r['estacion_id']: r for r in cur.fetchall()}
        con_dato = [e for e in estaciones if e['id'] in por_estacion]
        if not con_dato:
            return None, None, None, None
        e = min(con_dato, key=lambda e: e['_dist'])
        r = por_estacion[e['id']]
        return e, float(r['total']), None, r['n']
    else:
        # Agrega por día (las estaciones AUTOMATICA registran por hora) y
        # toma, por estación, el día más cercano a la fecha del evento.
        agg = _AGREGACION[variable]
        cur.execute(f"""
            SELECT estacion_id, fecha, {agg}({variable}) AS valor FROM registros_meteorologicos
            WHERE estacion_id = ANY(%s) AND fecha BETWEEN %s AND %s
                  AND {variable} IS NOT NULL {_filtro_rango(variable)}
            GROUP BY estacion_id, fecha
        """, (ids_estaciones, fecha - timedelta(days=2), fecha + timedelta(days=2)))
        filas = cur.fetchall()
        mejor_por_estacion = {}
        for fila in filas:
            eid = fila['estacion_id']
            dist_dias = abs((fila['fecha'] - fecha).days)
            actual = mejor_por_estacion.get(eid)
            if actual is None or dist_dias < actual[0]:
                mejor_por_estacion[eid] = (dist_dias, fila)
        con_dato = [e for e in estaciones if e['id'] in mejor_por_estacion]
        if not con_dato:
            return None, None, None, None
        e = min(con_dato, key=lambda e: e['_dist'])
        fila = mejor_por_estacion[e['id']][1]
        return e, float(fila['valor']), fila['fecha'], None


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

    capas = _capas_en_punto(evento, punto)
    # capas=[] es válido (ej. Temperatura Alta, sin capa geoespacial propia) —
    # placeholder seguro para que el frontend no truene leyendo data.capa.disponible.
    resultado['capa'] = capas[0] if capas else {
        'nombre': None, 'label': None, 'disponible': False, 'en_capa': False, 'nivel': None, 'color': None,
    }
    resultado['capas'] = capas     # lista completa (0 para eventos sin capa, 2 para Inundación, 1 el resto)
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
                # PP/Tmax/Tmin juntos (no solo la variable del evento) con P90/P95
                # del mes — pedido explícito para graficar en el detalle del caso.
                estacion_resultado['grafica'] = _grafica_estacion(cur, e['id'], fecha.month)

        cur.close(); conn.close()
    resultado['estacion'] = estacion_resultado

    # any(): en Inundación basta con caer en CUALQUIERA de las 2 capas
    # (Inundación o Río) para que cuente como señal — para el resto de
    # eventos "capas" trae un solo elemento, se comporta igual que antes.
    señales = [any(c['en_capa'] for c in capas), resultado['aviso'] is not None,
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


# ============================================================================
# PERFIL INSPECTOR — cola de siniestros reportados por agricultores (/siniestro/
# reportar), verificación caso por caso reusando el mismo motor de triple
# cruce (_verificar_punto), cruce con la tabla clientes por DNI, siniestros
# cercanos, y PDF de reporte.
# ============================================================================

# El agricultor elige el evento en español/con mayúscula (ver
# routes/siniestros_agricultor.py::EVENTOS_VALIDOS); EVENTOS (arriba) usa
# claves en minúscula para el motor de verificación. "Otro" no tiene capa de
# riesgo asociada — no se puede auto-verificar, el inspector decide a mano.
MAPA_EVENTO_SINIESTRO = {
    'Inundación': 'inundacion',
    'Huayco': 'huayco',
    'Sequía': 'sequia',
    'Helada': 'helada',
    'Friaje': 'friaje',
    'Viento Fuerte': 'viento',
    'Incendio Forestal': 'incendios',
    'Otro': None,
}

RADIO_CERCANOS_KM = 5


def _cliente_por_dni(dni):
    """Cruza el DNI del siniestro contra la tabla clientes: vigencia de
    póliza, cultivo, hectáreas, etc. — para que el inspector vea si quien
    reportó es realmente un cliente asegurado, y si lo que reportó cuadra."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT c.id, c.dni_ruc, c.nombre, c.apellido, c.telefono,
               c.departamento, c.provincia, c.distrito,
               c.hectareas, c.area_asegurada, c.monto_asegurado, c.suma_asegurada_tasa,
               c.variedad, c.fecha_siembra, c.fecha_cosecha,
               c.mes_inicio_vigencia, c.mes_fin_vigencia, c.tasa_reaseguro, c.prima_neta,
               c.estado, e.nombre AS entidad_nombre, tc.nombre AS cultivo_nombre
        FROM clientes c
        LEFT JOIN entidades e ON e.id = c.entidad_id
        LEFT JOIN tabla_cultivos tc ON tc.id = c.cultivo_id
        WHERE c.dni_ruc = %s
    """, (dni,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return None
    row['vigente'] = (row.get('estado') == 'activo')
    for campo in ('fecha_siembra', 'fecha_cosecha', 'mes_inicio_vigencia', 'mes_fin_vigencia'):
        if row.get(campo):
            row[campo] = row[campo].isoformat()

    # Exposición YA precalculada del cliente (botón "Actualizar Cruce" en Mapa
    # Clientes) — no se recalcula de nuevo acá, se reusa lo que ya existe.
    cur.execute("""
        SELECT capa, nivel FROM clientes_riesgo_capa WHERE cliente_id = %s
    """, (row['id'],))
    row['exposicion_precalculada'] = {r['capa']: r['nivel'] for r in cur.fetchall()}

    cur.close(); conn.close()
    return row


def _siniestros_cercanos(siniestro_id, lat, lon, radio_km=RADIO_CERCANOS_KM):
    """Otros siniestros dentro de radio_km — le sirve al inspector para ver
    si hay un patrón (varios reclamos del mismo evento en la misma zona) o
    una señal rara (un reclamo aislado lejos de todo lo demás)."""
    if lat is None or lon is None:
        return []
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    # Caja de +-1 grado (~110km) como pre-filtro barato antes del haversine exacto.
    cur.execute("""
        SELECT id, dni, nombre_completo, cultivo_afectado, evento, fecha_evento,
               latitud, longitud, estado
        FROM siniestros_agricultor
        WHERE id != %s AND latitud IS NOT NULL AND longitud IS NOT NULL
          AND latitud BETWEEN %s - 1 AND %s + 1
          AND longitud BETWEEN %s - 1 AND %s + 1
    """, (siniestro_id, lat, lat, lon, lon))
    candidatos = cur.fetchall()
    cur.close(); conn.close()

    cercanos = []
    for c in candidatos:
        dist = _haversine_km(lat, lon, float(c['latitud']), float(c['longitud']))
        if dist <= radio_km:
            c['distancia_km'] = round(dist, 1)
            c['fecha_evento'] = c['fecha_evento'].isoformat()
            c['latitud'] = float(c['latitud'])
            c['longitud'] = float(c['longitud'])
            cercanos.append(c)
    cercanos.sort(key=lambda c: c['distancia_km'])
    return cercanos


def _obtener_siniestro(siniestro_id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM siniestros_agricultor WHERE id = %s", (siniestro_id,))
    siniestro = cur.fetchone()
    if not siniestro:
        cur.close(); conn.close()
        return None
    cur.execute("""
        SELECT id, url_drive, latitud, longitud, subido_en
        FROM siniestros_agricultor_fotos WHERE siniestro_id = %s ORDER BY id
    """, (siniestro_id,))
    fotos = cur.fetchall()
    cur.close(); conn.close()
    return siniestro, fotos


@evaluacion_riesgo_bp.route('/siniestros', methods=['GET'])
@login_required
def siniestros_lista():
    return render_template('inspector_siniestros.html')


@evaluacion_riesgo_bp.route('/siniestros/<int:siniestro_id>', methods=['GET'])
@login_required
def siniestros_detalle(siniestro_id):
    return render_template('inspector_siniestro_detalle.html', siniestro_id=siniestro_id)


@evaluacion_riesgo_bp.route('/api/siniestros', methods=['GET'])
@login_required
def api_siniestros_lista():
    estado = request.args.get('estado', '').strip()
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    condiciones, params = [], []
    if estado:
        condiciones.append('estado = %s')
        params.append(estado)
    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ''
    cur.execute(f"""
        SELECT s.id, s.dni, s.nombre_completo, s.cultivo_afectado, s.alcance_dano,
               s.evento, s.fecha_evento, s.estado, s.creado_en,
               (SELECT count(*) FROM siniestros_agricultor_fotos f WHERE f.siniestro_id = s.id) AS total_fotos
        FROM siniestros_agricultor s
        {where}
        ORDER BY s.creado_en DESC
    """, params)
    filas = cur.fetchall()
    cur.close(); conn.close()
    for f in filas:
        f['fecha_evento'] = f['fecha_evento'].isoformat()
        f['creado_en'] = f['creado_en'].isoformat()
    return jsonify({'total': len(filas), 'siniestros': filas})


@evaluacion_riesgo_bp.route('/api/siniestros/<int:siniestro_id>', methods=['GET'])
@login_required
def api_siniestro_detalle(siniestro_id):
    datos = _obtener_siniestro(siniestro_id)
    if not datos:
        return jsonify({'error': 'Siniestro no encontrado'}), 404
    siniestro, fotos = datos

    resultado = dict(siniestro)
    resultado['fecha_evento'] = siniestro['fecha_evento'].isoformat()
    resultado['creado_en'] = siniestro['creado_en'].isoformat()
    resultado['evaluado_en'] = siniestro['evaluado_en'].isoformat() if siniestro['evaluado_en'] else None
    resultado['latitud'] = float(siniestro['latitud']) if siniestro['latitud'] is not None else None
    resultado['longitud'] = float(siniestro['longitud']) if siniestro['longitud'] is not None else None
    resultado['fotos'] = [
        {'id': f['id'], 'url_drive': f['url_drive'], 'subido_en': f['subido_en'].isoformat()}
        for f in fotos
    ]

    resultado['cliente'] = _cliente_por_dni(siniestro['dni'])
    resultado['cercanos'] = _siniestros_cercanos(siniestro_id, resultado['latitud'], resultado['longitud'])

    evento_id = MAPA_EVENTO_SINIESTRO.get(siniestro['evento'])
    if evento_id and resultado['latitud'] is not None:
        try:
            # con_detalle_meteo=True: ahora sí se pide completo (gráfica
            # mensual PP/Tmax/Tmin + percentil) — antes se evitaba porque la
            # búsqueda de estación hacía 1 consulta POR estación (lento); eso
            # ya se arregló (1 sola consulta para todas), así que pedir el
            # detalle acá ya no cuesta los 2-3 min de antes.
            resultado['verificacion'] = _verificar_punto(
                evento_id, siniestro['fecha_evento'], resultado['latitud'], resultado['longitud'],
                90, con_detalle_meteo=True)
        except Exception as e:
            logger.error('Error verificando siniestro %s: %s', siniestro_id, str(e))
            resultado['verificacion'] = {'error': str(e)}
    else:
        resultado['verificacion'] = None  # "Otro" o sin ubicación: no se puede auto-verificar

    return jsonify(resultado)


@evaluacion_riesgo_bp.route('/api/siniestros/<int:siniestro_id>/evaluar', methods=['POST'])
@login_required
def api_siniestro_evaluar(siniestro_id):
    data = request.get_json(force=True, silent=True) or {}
    estado = data.get('estado', '').strip()
    comentario = data.get('comentario', '').strip() or None

    if estado not in ('Verificado', 'Rechazado', 'Pendiente'):
        return jsonify({'error': 'Estado inválido'}), 400

    from flask_login import current_user
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE siniestros_agricultor
        SET estado = %s, comentario_inspector = %s, evaluado_por = %s, evaluado_en = now()
        WHERE id = %s
    """, (estado, comentario, current_user.username, siniestro_id))
    if cur.rowcount == 0:
        conn.rollback(); cur.close(); conn.close()
        return jsonify({'error': 'Siniestro no encontrado'}), 404
    conn.commit()
    cur.close(); conn.close()
    return jsonify({'status': 'ok'})


@evaluacion_riesgo_bp.route('/siniestros/<int:siniestro_id>/pdf', methods=['GET'])
@login_required
def siniestro_pdf(siniestro_id):
    from io import BytesIO
    from flask import send_file
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    datos = _obtener_siniestro(siniestro_id)
    if not datos:
        return jsonify({'error': 'Siniestro no encontrado'}), 404
    siniestro, fotos = datos

    cliente = _cliente_por_dni(siniestro['dni'])
    lat = float(siniestro['latitud']) if siniestro['latitud'] is not None else None
    lon = float(siniestro['longitud']) if siniestro['longitud'] is not None else None
    verificacion = None
    evento_id = MAPA_EVENTO_SINIESTRO.get(siniestro['evento'])
    if evento_id and lat is not None:
        try:
            verificacion = _verificar_punto(evento_id, siniestro['fecha_evento'], lat, lon, 90)
        except Exception:
            verificacion = None

    styles = getSampleStyleSheet()
    titulo = ParagraphStyle('titulo', parent=styles['Heading1'], textColor=colors.HexColor('#039e97'))
    subt = ParagraphStyle('subt', parent=styles['Heading2'], textColor=colors.HexColor('#2c3e50'), fontSize=12)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    elementos = [
        Paragraph('Reporte de Siniestro — La Positiva AgroSeguros', titulo),
        Paragraph(f'Siniestro N° {siniestro_id} &nbsp;&nbsp;|&nbsp;&nbsp; Estado: {siniestro["estado"]}', styles['Normal']),
        Spacer(1, 0.5*cm),
        Paragraph('Datos del agricultor', subt),
        Table([
            ['DNI', siniestro['dni']],
            ['Nombre completo', siniestro['nombre_completo']],
            ['Celular(es)', f"{siniestro['celular1']}" + (f" / {siniestro['celular2']}" if siniestro['celular2'] else '')],
            ['Correo', siniestro['correo'] or '-'],
        ], colWidths=[5*cm, 11*cm], style=TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey), ('BACKGROUND', (0,0), (0,-1), colors.whitesmoke)])),
        Spacer(1, 0.4*cm),
        Paragraph('Evento reportado', subt),
        Table([
            ['Cultivo afectado', siniestro['cultivo_afectado']],
            ['Alcance del daño', siniestro['alcance_dano']],
            ['Evento', siniestro['evento']],
            ['Fecha del evento', siniestro['fecha_evento'].strftime('%d/%m/%Y')],
            ['Ubicación (lat, lon)', f'{lat}, {lon}' if lat is not None else 'No disponible'],
            ['Cantidad de fotos', str(len(fotos))],
        ], colWidths=[5*cm, 11*cm], style=TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey), ('BACKGROUND', (0,0), (0,-1), colors.whitesmoke)])),
        Spacer(1, 0.4*cm),
    ]

    elementos.append(Paragraph('Cruce con póliza (tabla clientes)', subt))
    if cliente:
        elementos.append(Table([
            ['¿Es cliente asegurado?', 'Sí'],
            ['Vigente', 'Sí' if cliente['vigente'] else 'No'],
            ['Nombre registrado', f"{cliente['nombre']} {cliente['apellido']}"],
            ['Cultivo registrado', cliente['cultivo_nombre'] or '-'],
            ['Hectáreas aseguradas', str(cliente['hectareas']) if cliente['hectareas'] else '-'],
            ['Suma asegurada', f"S/ {cliente['monto_asegurado']}" if cliente['monto_asegurado'] else '-'],
            ['Entidad financiera', cliente['entidad_nombre'] or '-'],
        ], colWidths=[5*cm, 11*cm], style=TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey), ('BACKGROUND', (0,0), (0,-1), colors.whitesmoke)])))
    else:
        elementos.append(Paragraph('⚠️ El DNI no se encuentra en la base de clientes asegurados.', styles['Normal']))
    elementos.append(Spacer(1, 0.4*cm))

    elementos.append(Paragraph('Verificación automática (capa de riesgo + aviso SENAMHI + estación)', subt))
    if verificacion and 'error' not in verificacion:
        elementos.append(Table([
            ['Veredicto', 'RESPALDADO por datos' if verificacion['veredicto'] else 'NO respaldado por datos'],
            ['Señales positivas', f"{verificacion['señales_positivas']} de 3"],
            ['Capa de riesgo', ', '.join(f"{c['label']}: {'Sí, nivel ' + c['nivel'] if c['en_capa'] else 'No expuesto'}" for c in verificacion['capas']) or '-'],
            ['Aviso SENAMHI vigente', 'Sí' if verificacion['aviso'] else 'No'],
            ['Estación meteorológica', f"{verificacion['estacion']['estacion']} ({verificacion['estacion']['distancia_km']} km)" if verificacion['estacion'] else 'Sin dato cercano'],
        ], colWidths=[5*cm, 11*cm], style=TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey), ('BACKGROUND', (0,0), (0,-1), colors.whitesmoke)])))
    else:
        elementos.append(Paragraph('No se pudo calcular (evento "Otro" o sin ubicación) — requiere evaluación manual.', styles['Normal']))
    elementos.append(Spacer(1, 0.4*cm))

    elementos.append(Paragraph('Evaluación del inspector', subt))
    elementos.append(Table([
        ['Estado', siniestro['estado']],
        ['Evaluado por', siniestro['evaluado_por'] or '-'],
        ['Fecha de evaluación', siniestro['evaluado_en'].strftime('%d/%m/%Y %H:%M') if siniestro['evaluado_en'] else '-'],
        ['Comentario', siniestro['comentario_inspector'] or '-'],
    ], colWidths=[5*cm, 11*cm], style=TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey), ('BACKGROUND', (0,0), (0,-1), colors.whitesmoke)])))

    doc.build(elementos)
    buf.seek(0)
    return send_file(buf, mimetype='application/pdf', as_attachment=True,
                      download_name=f'siniestro_{siniestro_id}_reporte.pdf')
