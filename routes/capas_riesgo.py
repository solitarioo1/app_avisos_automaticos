"""
routes/capas_riesgo.py — Selector de capa de riesgo para Mapa Clientes (Decisiones).

Arquitectura (decisión del usuario, 27 ago 2026): las capas de peligro son
FIJAS (casi no cambian), lo que cambia constantemente son los clientes (sync
mensual del Sheet) y los avisos. Por eso el cruce cliente<->capa NO se
recalcula en cada carga de página — se calcula una vez con /recalcular
(botón "Actualizar Cruce" en la UI) y queda guardado en la tabla
`clientes_riesgo_capa`. Los endpoints de KPIs/geojson solo LEEN de esa tabla
(rápido, sin geopandas de por medio).

Independiente del flujo por aviso (routes/decisiones.py): acá el cruce es
capa de peligro <-> todos los clientes, no aviso vigente <-> zonas afectadas.
"""
import csv
import io
import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd
import psycopg2.extras
from flask import Blueprint, Response, jsonify, request
from shapely.geometry import Point

from CONFIG.db import get_connection

logger = logging.getLogger(__name__)
capas_riesgo_bp = Blueprint('capas_riesgo', __name__, url_prefix='')

BASE_DIR = Path(__file__).parent.parent
CLIP_DIR = BASE_DIR / 'CAPAS' / 'CAPAS_PROCESADAS'
DEPARTAMENTOS_SHP = BASE_DIR / 'DELIMITACIONES' / 'DEPARTAMENTOS' / 'DEPARTAMENTOS.shp'


def _filtro_niveles():
    """?niveles=Muy Alto,Alto — filtro opcional para combinar solo los niveles
    elegidos en KPIs/mapa/tablas de Capas de Riesgo. Vacío = todos (default)."""
    niveles_raw = request.args.get('niveles', '')
    return [n.strip() for n in niveles_raw.split(',') if n.strip()]


def _filtro_capa_extra(cur_condiciones, cur_params):
    """Agrega a una condición/params ya armados (que ya trae 'r.capa = %s') los
    filtros opcionales de zona (depto/provincia/distrito) y entidad — los mismos
    que ya se usan en Mapa Clientes para Avisos, ahora también en Capas de
    Riesgo: antes elegir depto/provincia/distrito en modo Capas no filtraba
    nada (el bloque "Estadísticas" del panel se quedaba siempre en cero)."""
    condiciones, params = list(cur_condiciones), list(cur_params)
    niveles = _filtro_niveles()
    if niveles:
        condiciones.append('r.nivel = ANY(%s)')
        params.append(niveles)
    for campo_url, columna in [('depto', 'c.departamento'), ('provincia', 'c.provincia'), ('distrito', 'c.distrito')]:
        valor = request.args.get(campo_url)
        if valor:
            condiciones.append(f'{columna} ILIKE %s')
            params.append(valor)
    entidad_id = request.args.get('entidad_id')
    if entidad_id:
        condiciones.append('c.entidad_id = %s')
        params.append(entidad_id)
    return condiciones, params

# Registro de capas disponibles para el selector del Mapa Clientes.
# campo_categoria: columna del GeoJSON con severidad/nivel (None si no aplica).
CAPAS_DISPONIBLES = {
    # friaje/helada/sequia/viento/incendios: *_raw.geojson = capa cruda de SENAMHI/CENPRED
    # (sin cruzar con zona agrícola) — el cruce generaba huecos/recortes falsos
    # en los polígonos (ver feedback_no_cruzar_capa_agraria). Son livianas (<10k
    # features), se leen enteras sin necesidad de fragmentar.
    'friaje':     {'label': 'Friaje',              'archivo': 'friaje_raw.geojson',           'campo_categoria': 'susc_friaj', 'color': '#d35400'},
    'helada':     {'label': 'Helada',               'archivo': 'helada_raw.geojson',           'campo_categoria': 'gridcode',   'color': '#3498db'},
    'sequia':     {'label': 'Sequía Meteorológica', 'archivo': 'sequia_raw.geojson',           'campo_categoria': 'nivel',      'color': '#e67e22'},
    'viento':     {'label': 'Viento Fuerte',        'archivo': 'viento_raw.geojson',           'campo_categoria': 'nivel',      'color': '#16a085'},
    'incendios':  {'label': 'Incendios Forestales', 'archivo': 'incendios_raw.geojson',        'campo_categoria': 'cod_niv',    'color': '#c0392b'},
    'rio':        {'label': 'Faja Marginal (Río)',  'archivo': 'rio_principal_buffer.geojson', 'campo_categoria': 'nivel',      'color': '#2980b9'},
    'inundacion': {'label': 'Inundación',           'archivo': 'inundacion_raw.gpkg',          'campo_categoria': 'nsief_pfen', 'color': '#2c3e50'},
    'mov_masa':   {'label': 'Movimiento de Masa',   'archivo': 'mov_masa_raw.gpkg',            'campo_categoria': 'nsmm_pfen',  'color': '#7f8c8d'},
}

# Versión liviana (disuelta por nivel + simplificada) de cada capa, para pintar
# el polígono de la zona de peligro en el mapa (no solo los puntos de clientes).
# Para friaje/helada/sequia/viento/incendios ya es tan liviana (<10k features)
# que se reusa el mismo *_raw.geojson tal cual, sin necesidad de un preview aparte.
ARCHIVO_PREVIEW = {
    'friaje': 'friaje_raw.geojson',
    'helada': 'helada_raw.geojson',
    'sequia': 'sequia_raw.geojson',
    'viento': 'viento_raw.geojson',
    'incendios': 'incendios_raw.geojson',
    'rio': 'rio_principal_buffer.geojson',  # bandas por distancia (<10/50/100/300/500m), ya liviana
    'inundacion': 'inundacion_raw_preview.geojson',
    'mov_masa': 'mov_masa_raw_preview.geojson',
}

# ============================================================================
# Estandarización de niveles — cada capa trae su propia escala cruda (algunas
# con 5-6 categorías en texto, otras códigos numéricos sin significado propio).
# Todo se normaliza a 4 niveles fijos para que Mapa Clientes y Evaluación de
# Riesgo muestren siempre lo mismo, sin importar de qué capa venga el dato.
# ============================================================================
NIVELES_ESTANDAR = ['Muy Alto', 'Alto', 'Medio', 'Bajo']

# Categorías en texto (friaje/sequía/viento/río/inundación) -> nivel estándar.
# "Bajo" y "Muy bajo" se funden en uno solo; "No aplica" (sequía) se trata como
# el peligro más bajo (decisión: no aparecer en el estudio de riesgo suele
# significar que no aplica ese peligro ahí, no que falte evaluar).
_MAPA_NIVEL_TEXTO = {
    'muy alto': 'Muy Alto', 'muy alta': 'Muy Alto', 'severo': 'Muy Alto', 'extremo': 'Muy Alto',
    'alto': 'Alto', 'alta': 'Alto',
    'medio': 'Medio', 'media': 'Medio', 'moderado': 'Medio',
    'bajo': 'Bajo', 'baja': 'Bajo',
    'muy bajo': 'Bajo', 'muy baja': 'Bajo',
    'bajo a muy bajo': 'Bajo',
    'no aplica': 'Bajo',
}

# Capas con código numérico (sin texto propio): mapeo explícito por capa, ya
# que la escala real (cuántos niveles, en qué orden) varía entre ellas.
_MAPA_NIVEL_NUMERICO = {
    'helada':    {1: 'Bajo', 2: 'Bajo', 3: 'Medio', 4: 'Alto', 5: 'Muy Alto'},
    'incendios': {1: 'Bajo', 2: 'Medio', 3: 'Alto', 4: 'Muy Alto', 5: 'Muy Alto'},
}

_COLOR_NIVEL_ESTANDAR = {'Muy Alto': '#c0392b', 'Alto': '#e67e22', 'Medio': '#f1c40f', 'Bajo': '#2ecc71'}


def _nivel_estandar(capa, valor):
    """Normaliza el valor crudo (texto o numérico) de una capa a uno de los
    4 niveles estándar: Muy Alto / Alto / Medio / Bajo. None si no se reconoce."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    txt = str(valor).strip().lower()
    if txt in _MAPA_NIVEL_TEXTO:
        return _MAPA_NIVEL_TEXTO[txt]
    try:
        n = int(float(valor))
    except (TypeError, ValueError):
        return None
    return _MAPA_NIVEL_NUMERICO.get(capa, {}).get(n)


def _color_por_nivel(capa, valor):
    """Color verde->rojo del nivel estandarizado de esa capa."""
    return _COLOR_NIVEL_ESTANDAR.get(_nivel_estandar(capa, valor), '#dddddd')


def _cargar_capa(nombre):
    """Carga una capa recortada por nombre (solo se usa durante /recalcular)."""
    info = CAPAS_DISPONIBLES.get(nombre)
    if not info:
        return None
    ruta = CLIP_DIR / info['archivo']
    if not ruta.exists():
        return None
    gdf = gpd.read_file(ruta)
    if gdf.crs is None:
        gdf = gdf.set_crs('EPSG:4326')
    return gdf


def _cargar_clientes_gdf():
    """Trae todos los clientes con coordenadas válidas como GeoDataFrame de puntos."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.latitud, c.longitud
        FROM clientes c
        WHERE c.latitud IS NOT NULL AND c.longitud IS NOT NULL
          AND c.estado = 'activo'
    """)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    cur.close()
    conn.close()

    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        return gpd.GeoDataFrame(df, geometry=[], crs='EPSG:4326')

    df['latitud'] = df['latitud'].astype(float)
    df['longitud'] = df['longitud'].astype(float)

    return gpd.GeoDataFrame(
        df, geometry=gpd.points_from_xy(df['longitud'], df['latitud']), crs='EPSG:4326'
    )


def _recalcular_capa(nombre, clientes_gdf):
    """Cruza una capa contra los clientes y guarda el resultado en clientes_riesgo_capa.
    Devuelve la cantidad de clientes expuestos, o None si la capa no está lista."""
    info = CAPAS_DISPONIBLES.get(nombre)
    capa = _cargar_capa(nombre)
    if capa is None:
        return None

    conn = get_connection()
    cur = conn.cursor()

    if clientes_gdf.empty:
        cur.execute("DELETE FROM clientes_riesgo_capa WHERE capa = %s", (nombre,))
        conn.commit()
        cur.close(); conn.close()
        return 0

    cruce = gpd.sjoin(clientes_gdf, capa, how='inner', predicate='within')
    cruce = cruce.drop_duplicates(subset='id')  # cliente en 2 polígonos superpuestos -> 1 sola fila

    campo_cat = info.get('campo_categoria')
    filas = []
    ids_expuestos = set()
    for _, row in cruce.iterrows():
        valor_crudo = row.get(campo_cat) if campo_cat and campo_cat in cruce.columns else None
        nivel = _nivel_estandar(nombre, valor_crudo)  # guardado ya estandarizado (Muy Alto/Alto/Medio/Bajo)
        filas.append((int(row['id']), nombre, nivel))
        ids_expuestos.add(int(row['id']))

    # Río: el archivo solo trae 3 bandas explícitas (Muy Alto/Alto/Medio,
    # hasta 1km) — dibujar "Bajo" como polígono nacional sería gigante/pesado.
    # Todo cliente que no cayó en esas 3 bandas es Bajo por definición (mismo
    # criterio que evaluacion_riesgo.py y clasificar-excel): en Mapa Clientes,
    # "Bajo" para río termina cubriendo a casi todos, y eso es correcto — es
    # justamente el punto, la mayoría no está cerca de un río.
    if nombre == 'rio':
        for _, row in clientes_gdf.iterrows():
            if int(row['id']) not in ids_expuestos:
                filas.append((int(row['id']), nombre, 'Bajo'))

    # Reemplazar todo lo anterior de esta capa por el resultado fresco.
    cur.execute("DELETE FROM clientes_riesgo_capa WHERE capa = %s", (nombre,))
    if filas:
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO clientes_riesgo_capa (cliente_id, capa, nivel, calculado_en) VALUES %s",
            filas,
            template="(%s, %s, %s, now())"
        )
    conn.commit()
    cur.close()
    conn.close()
    return len(filas)


@capas_riesgo_bp.route('/api/capas-riesgo/disponibles', methods=['GET'])
def api_capas_disponibles():
    """Lista las capas para el selector, marcando cuáles ya están listas y su último cálculo."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT capa, max(calculado_en), count(*) FROM clientes_riesgo_capa GROUP BY capa")
    estados = {r[0]: {'calculado_en': r[1].isoformat(), 'total': r[2]} for r in cur.fetchall()}
    cur.close(); conn.close()

    disponibles = []
    for key, info in CAPAS_DISPONIBLES.items():
        # "Disponible" = lo que hace falta para mostrar la capa en Mapa Clientes
        # y en Clasifica tu Cliente: el archivo _preview (liviano). El _clip
        # pesado solo hace falta para el botón "Actualizar Cruce" (recálculo),
        # que no requiere estar presente en cada servidor — la BD ya trae el
        # resultado (clientes_riesgo_capa se comparte entre local y VPS).
        archivo_preview = ARCHIVO_PREVIEW.get(key)
        existe = bool(archivo_preview) and (CLIP_DIR / archivo_preview).exists()
        estado = estados.get(key)
        disponibles.append({
            'id': key, 'label': info['label'], 'color': info['color'],
            'disponible': existe,
            'calculado': estado is not None,
            'calculado_en': estado['calculado_en'] if estado else None,
            'total_calculado': estado['total'] if estado else 0,
        })
    return jsonify(disponibles)


@capas_riesgo_bp.route('/api/capas-riesgo/recalcular', methods=['POST'])
def api_recalcular():
    """Cruza contra los clientes actuales y guarda el resultado. Se llama
    manualmente (botón 'Actualizar Cruce'), no automáticamente — las capas son
    fijas, lo que cambia es la data de clientes.

    Por defecto recorre TODAS las capas disponibles (comportamiento original).
    Si se manda ?capa=<nombre> (o body JSON {"capa": "<nombre>"}), recalcula
    solo esa una — útil para no esperar 15-20 min (Viento/Incendios pesan
    ~1GB cada uno) cuando solo cambió/se corrigió una capa puntual."""
    capa_unica = request.args.get('capa') or (request.get_json(silent=True) or {}).get('capa')
    if capa_unica and capa_unica not in CAPAS_DISPONIBLES:
        return jsonify({'error': f'Capa "{capa_unica}" no existe'}), 400

    try:
        clientes_gdf = _cargar_clientes_gdf()
        resultados = {}
        items = {capa_unica: CAPAS_DISPONIBLES[capa_unica]} if capa_unica else CAPAS_DISPONIBLES
        for nombre, info in items.items():
            ruta = CLIP_DIR / info['archivo']
            if not ruta.exists():
                resultados[nombre] = {'estado': 'no_disponible'}
                continue
            try:
                total = _recalcular_capa(nombre, clientes_gdf)
                resultados[nombre] = {'estado': 'ok', 'total_expuestos': total}
            except Exception as e:
                logger.error("Error recalculando capa %s: %s", nombre, str(e))
                resultados[nombre] = {'estado': 'error', 'detalle': str(e)}
        return jsonify({'total_clientes_procesados': len(clientes_gdf), 'resultados': resultados})
    except Exception as e:
        logger.error("Error en recalcular: %s", str(e))
        return jsonify({'error': str(e)}), 500


@capas_riesgo_bp.route('/api/capas-riesgo/<nombre>/kpis', methods=['GET'])
def api_kpis_por_capa(nombre):
    """KPIs de clientes expuestos a la capa — lee de la tabla ya calculada, no recruza en vivo."""
    info = CAPAS_DISPONIBLES.get(nombre)
    if info is None:
        return jsonify({'error': f'Capa "{nombre}" no existe'}), 404
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Totales de TODA la BD (independiente de la capa) — igual que hace
        # /api/avisos/<numero>/kpis. Antes el frontend los sacaba del DOM ya
        # pintado por el flujo de avisos, así que si se entraba directo a
        # "Capas de Riesgo" sin pasar por un aviso primero, quedaban en "-".
        cur.execute("""
            SELECT COUNT(*) AS total, COALESCE(SUM(hectareas), 0) AS ha, COALESCE(SUM(monto_asegurado), 0) AS monto
            FROM clientes
            WHERE estado = 'activo'
        """)
        totales = cur.fetchone()

        condiciones, params = _filtro_capa_extra(['r.capa = %s'], [nombre])
        cur.execute(f"""
            SELECT r.nivel, c.departamento, c.hectareas, c.monto_asegurado
            FROM clientes_riesgo_capa r
            JOIN clientes c ON c.id = r.cliente_id
            WHERE {' AND '.join(condiciones)}
        """, params)
        rows = cur.fetchall()
        cur.close(); conn.close()

        base = {
            'capa': nombre, 'label': info['label'],
            'agricultores_totales': int(totales['total']),
            'hectareas_totales': round(float(totales['ha']), 2),
            'poliza_total': round(float(totales['monto']), 2),
        }

        if not rows:
            return jsonify({**base, 'total_expuestos': 0, 'hectareas_expuestas': 0, 'monto_expuesto': 0})

        df = pd.DataFrame(rows)
        # por_categoria/por_departamento se quitaron: no los leía nadie en el
        # frontend (quedaron huérfanos desde que se borró el cuadrito de
        # resumen) — ese desglose ya lo muestra la tabla de Zonas (/zonas).
        return jsonify({
            **base,
            'total_expuestos': len(df),
            'hectareas_expuestas': round(float(df['hectareas'].astype(float).sum()), 2),
            'monto_expuesto': round(float(df['monto_asegurado'].astype(float).sum()), 2),
        })
    except Exception as e:
        logger.error("Error consultando KPIs por capa %s: %s", nombre, str(e))
        return jsonify({'error': str(e)}), 500


@capas_riesgo_bp.route('/api/capas-riesgo/<nombre>/clientes-geojson', methods=['GET'])
def api_clientes_por_capa_geojson(nombre):
    """Clientes expuestos a la capa (ya calculado), como GeoJSON para pintar en el mapa."""
    info = CAPAS_DISPONIBLES.get(nombre)
    if info is None:
        return jsonify({'error': f'Capa "{nombre}" no existe'}), 404
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        condiciones, params = _filtro_capa_extra(['r.capa = %s'], [nombre])
        cur.execute(f"""
            SELECT c.id, c.nombre, c.apellido, c.latitud, c.longitud,
                   c.departamento, c.provincia, c.distrito,
                   c.hectareas, c.monto_asegurado, e.nombre AS entidad_nombre, r.nivel
            FROM clientes_riesgo_capa r
            JOIN clientes c ON c.id = r.cliente_id
            LEFT JOIN entidades e ON e.id = c.entidad_id
            WHERE {' AND '.join(condiciones)}
        """, params)
        rows = cur.fetchall()
        cur.close(); conn.close()

        features = []
        for r in rows:
            features.append({
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [float(r['longitud']), float(r['latitud'])]},
                'properties': {
                    'id': r['id'],  # para cruzar contra clientesLayer y pintar azul/plomo en el mapa base
                    'nombre': f"{r.get('nombre','')} {r.get('apellido','')}",
                    'departamento': r.get('departamento', ''),
                    'provincia': r.get('provincia', ''),
                    'distrito': r.get('distrito', ''),
                    'hectareas': r.get('hectareas'),
                    'monto_asegurado': r.get('monto_asegurado'),
                    'entidad_nombre': r.get('entidad_nombre', ''),
                    'nivel': r.get('nivel'),
                }
            })
        return jsonify({'type': 'FeatureCollection', 'features': features, 'total': len(features)})
    except Exception as e:
        logger.error("Error generando geojson por capa %s: %s", nombre, str(e))
        return jsonify({'error': str(e)}), 500


@capas_riesgo_bp.route('/api/capas-riesgo/<nombre>/exportar-csv', methods=['GET'])
def api_exportar_csv_capa(nombre):
    """CSV descargable de los clientes expuestos a la capa, con su nivel de
    riesgo — para que el usuario pueda trabajar la lista fuera de la app."""
    info = CAPAS_DISPONIBLES.get(nombre)
    if info is None:
        return jsonify({'error': f'Capa "{nombre}" no existe'}), 404
    try:
        # Mismos filtros que están puestos en pantalla (Mapa Clientes) — el
        # CSV tiene que salir acotado igual que lo que se está viendo, no el
        # cruce completo sin filtrar.
        condiciones, params = _filtro_capa_extra(['r.capa = %s'], [nombre])

        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(f"""
            SELECT c.id, c.nombre, c.apellido, c.dni_ruc, c.telefono, c.correo, r.nivel,
                   c.departamento, c.provincia, c.distrito,
                   c.hectareas, c.monto_asegurado, e.nombre AS entidad_nombre,
                   tc.nombre AS cultivo_nombre
            FROM clientes_riesgo_capa r
            JOIN clientes c ON c.id = r.cliente_id
            LEFT JOIN entidades e ON e.id = c.entidad_id
            LEFT JOIN tabla_cultivos tc ON tc.id = c.cultivo_id
            WHERE {' AND '.join(condiciones)}
            ORDER BY CASE r.nivel
                WHEN 'Muy Alto' THEN 1 WHEN 'Alto' THEN 2 WHEN 'Medio' THEN 3 WHEN 'Bajo' THEN 4 ELSE 5
            END, c.departamento, c.provincia, c.distrito
        """, params)
        rows = cur.fetchall()
        cur.close(); conn.close()

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['ID', 'Nombre', 'Apellido', 'DNI/RUC', 'Telefono', 'Correo', 'Nivel de Riesgo',
                          'Departamento', 'Provincia', 'Distrito', 'Hectareas', 'Monto Asegurado',
                          'Entidad', 'Cultivo'])
        for r in rows:
            writer.writerow([
                r['id'], r.get('nombre', ''), r.get('apellido', ''), r.get('dni_ruc', ''),
                r.get('telefono', ''), r.get('correo', ''),
                r.get('nivel', ''), r.get('departamento', ''), r.get('provincia', ''), r.get('distrito', ''),
                r.get('hectareas', ''), r.get('monto_asegurado', ''), r.get('entidad_nombre', ''),
                r.get('cultivo_nombre', ''),
            ])

        # BOM al inicio para que Excel abra los acentos/ñ bien en UTF-8.
        resp = Response('﻿' + buf.getvalue(), mimetype='text/csv')
        resp.headers['Content-Type'] = 'text/csv; charset=utf-8'  # evita que Flask duplique el charset
        # nombre (no info['label']) para el archivo: sin tildes, sin problema de encoding en el header.
        resp.headers['Content-Disposition'] = f'attachment; filename="clientes_{nombre}.csv"'
        return resp
    except Exception as e:
        logger.error("Error exportando CSV de capa %s: %s", nombre, str(e))
        return jsonify({'error': str(e)}), 500


_capa_preview_gdf_cache = {}  # nombre -> GeoDataFrame liviano (preview) cacheado, para clasificar-excel


def _cargar_capa_preview_gdf(nombre):
    if nombre in _capa_preview_gdf_cache:
        return _capa_preview_gdf_cache[nombre]
    archivo = ARCHIVO_PREVIEW.get(nombre)
    ruta = CLIP_DIR / archivo if archivo else None
    gdf = gpd.read_file(ruta) if ruta and ruta.exists() else None
    _capa_preview_gdf_cache[nombre] = gdf
    return gdf


_capa_completa_gdf_cache = {}  # nombre -> GeoDataFrame completo (sin simplificar), cacheado
_CAPAS_CON_VERSION_PESADA = {'inundacion', 'mov_masa'}  # unicas con archivo completo distinto del preview


def _cargar_capa_completa_cached(nombre):
    """Como _cargar_capa_preview_gdf, pero para Inundación/Mov. Masa sirve el
    archivo COMPLETO (sin simplificar con mapshaper), no el preview liviano —
    para dar una respuesta definitiva de exposición (Evaluación de Afiliaciones)
    no conviene perder precisión de borde de polígono solo por velocidad de
    mapa. El resto de capas no tiene esa distinción (su raw ya es liviano), se
    reusa el mismo preview de siempre. Se cachea en memoria — el archivo pesado
    (hasta 1.1GB) se lee una sola vez, nunca por request."""
    if nombre not in _CAPAS_CON_VERSION_PESADA:
        return _cargar_capa_preview_gdf(nombre)
    if nombre in _capa_completa_gdf_cache:
        return _capa_completa_gdf_cache[nombre]
    info = CAPAS_DISPONIBLES.get(nombre)
    ruta = CLIP_DIR / info['archivo'] if info else None
    gdf = gpd.read_file(ruta) if ruta and ruta.exists() else None
    if gdf is not None and gdf.crs is None:
        gdf = gdf.set_crs('EPSG:4326')
    _capa_completa_gdf_cache[nombre] = gdf
    return gdf


# NOTA: la clasificación de Excel de prospectos (antes acá, /clasificar-excel)
# se movió a routes/clasificar_cliente.py — pasó a evaluar contra TODAS las
# capas (no solo 1) + siniestros cercanos, para ser consistente con el flujo
# de fotos. Ver clasificar_cliente.py::api_clasificar_excel.


_cache_preview = {}  # nombre -> GeoDataFrame SIN filtrar (se cachea una vez, liviana)
_cache_geometria_depto = {}  # (nombre, depto) -> GeoJSON dict ya recortado+coloreado


def _cargar_capa_preview_gdf_nacional(nombre):
    if nombre in _cache_preview:
        return _cache_preview[nombre]
    archivo = ARCHIVO_PREVIEW.get(nombre)
    ruta = CLIP_DIR / archivo if archivo else None
    gdf = gpd.read_file(ruta) if ruta and ruta.exists() else None
    # OJO: la geometría YA viene reparada desde el archivo (mapshaper -clean
    # al generarlo) — hacer esto en Python con make_valid()/buffer(0) acá
    # tardaba 13-15 MIN para Inundación (demasiados vértices para GEOS en
    # Python); mapshaper lo resuelve en ~1 min. Si vuelve a salir
    # TopologyException al hacer clip(), hay que re-generar el archivo con
    # `mapshaper <preview.geojson> -clean -o <preview.geojson> force`,
    # no agregar reparación acá de nuevo.
    _cache_preview[nombre] = gdf
    return gdf


@capas_riesgo_bp.route('/api/capas-riesgo/<nombre>/geometria', methods=['GET'])
def api_geometria_capa(nombre):
    """Polígono de la zona de peligro en sí (disuelto por nivel, simplificado),
    coloreado verde->rojo según severidad. Esto es lo que se ve como 'mancha'
    en el mapa — separado de clientes-geojson, que son los puntos de clientes.

    OJO: requiere `depto` — mandar la capa completa (todo el Perú) de una sola
    vez reventaba el servidor/navegador (Inundación: ~26MB de geojson, varios
    cientos de miles de vértices) — ver feedback del 1 oct 2026. Sin `depto`
    no se devuelve geometría (el frontend no debe pintar nada a nivel nacional)."""
    info = CAPAS_DISPONIBLES.get(nombre)
    if info is None:
        return jsonify({'error': f'Capa "{nombre}" no existe'}), 404

    depto = (request.args.get('depto') or '').strip().upper()
    if not depto:
        return jsonify({'error': 'Selecciona un departamento para ver la capa', 'type': 'FeatureCollection', 'features': []}), 200

    cache_key = (nombre, depto)
    if cache_key in _cache_geometria_depto:
        return jsonify(_cache_geometria_depto[cache_key])

    gdf_nacional = _cargar_capa_preview_gdf_nacional(nombre)
    if gdf_nacional is None or gdf_nacional.empty:
        return jsonify({'error': f'Geometría de "{nombre}" no disponible todavía'}), 404

    try:
        deptos_gdf = gpd.read_file(DEPARTAMENTOS_SHP)[['DPTONOM02', 'geometry']]
        if deptos_gdf.crs is None or deptos_gdf.crs.to_epsg() != 4326:
            deptos_gdf = deptos_gdf.to_crs(4326)
        match = deptos_gdf[deptos_gdf['DPTONOM02'].str.upper() == depto]
        if match.empty:
            return jsonify({'error': f'Departamento "{depto}" no reconocido'}), 400

        gdf = gpd.clip(gdf_nacional, match)
        campo_cat = info.get('campo_categoria')
        geojson = gdf.__geo_interface__
        for feature in geojson['features']:
            valor = feature['properties'].get(campo_cat) if campo_cat else None
            nivel_std = _nivel_estandar(nombre, valor) if campo_cat else None
            feature['properties']['color_display'] = _COLOR_NIVEL_ESTANDAR.get(nivel_std, info['color']) if campo_cat else info['color']
            feature['properties']['nivel_display'] = nivel_std or valor
        _cache_geometria_depto[cache_key] = geojson
        return jsonify(geojson)
    except Exception as e:
        logger.error("Error cargando geometría de %s (depto=%s): %s", nombre, depto, str(e))
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Tablas inferiores (Zonas / Entidades / Cultivos) — mismo formato que las
# versiones por aviso en routes/decisiones.py, pero cruzando contra la capa
# de riesgo seleccionada en vez del aviso vigente. Así el flujo completo
# (KPIs de arriba + las 3 tablas de abajo) cambia igual al elegir una capa,
# tal como ya pasa al elegir un aviso.
# ============================================================================

@capas_riesgo_bp.route('/api/capas-riesgo/<nombre>/zonas', methods=['GET'])
def api_zonas_por_capa(nombre):
    """Clientes expuestos agrupados por nivel de la capa (Muy bajo..Muy alto)."""
    info = CAPAS_DISPONIBLES.get(nombre)
    if info is None:
        return jsonify({'error': f'Capa "{nombre}" no existe'}), 404
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        condiciones, params = _filtro_capa_extra(['r.capa = %s'], [nombre])
        cur.execute(f"""
            SELECT COALESCE(r.nivel, 'Expuesto') AS nivel,
                   COUNT(*) AS agricultores,
                   COALESCE(SUM(c.hectareas), 0) AS hectareas,
                   COALESCE(SUM(c.monto_asegurado), 0) AS monto
            FROM clientes_riesgo_capa r
            JOIN clientes c ON c.id = r.cliente_id
            WHERE {' AND '.join(condiciones)}
            GROUP BY COALESCE(r.nivel, 'Expuesto')
        """, params)
        rows = cur.fetchall()
        cur.close(); conn.close()

        zonas = {r['nivel']: {
            'agricultores': int(r['agricultores']),
            'hectareas': round(float(r['hectareas']), 2),
            'monto': round(float(r['monto']), 2),
        } for r in rows}
        return jsonify({'capa': nombre, 'zonas': zonas})
    except Exception as e:
        logger.error("Error zonas por capa %s: %s", nombre, str(e))
        return jsonify({'error': str(e)}), 500


@capas_riesgo_bp.route('/api/capas-riesgo/<nombre>/entidades', methods=['GET'])
def api_entidades_por_capa(nombre):
    """Entidades con clientes expuestos a la capa, % daño = expuestos / total de la entidad."""
    info = CAPAS_DISPONIBLES.get(nombre)
    if info is None:
        return jsonify({'error': f'Capa "{nombre}" no existe'}), 404
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        condiciones, params = _filtro_capa_extra(['r.capa = %s'], [nombre])
        cur.execute(f"""
            SELECT afc.entidad_id, afc.entidad_nombre, afc.agricultores_afectados,
                   afc.hectareas, afc.monto, tot.total_clientes_entidad
            FROM (
                SELECT c.entidad_id, e.nombre AS entidad_nombre,
                       COUNT(*) AS agricultores_afectados,
                       COALESCE(SUM(c.hectareas), 0) AS hectareas,
                       COALESCE(SUM(c.monto_asegurado), 0) AS monto
                FROM clientes_riesgo_capa r
                JOIN clientes c ON c.id = r.cliente_id
                LEFT JOIN entidades e ON e.id = c.entidad_id
                WHERE {' AND '.join(condiciones)}
                GROUP BY c.entidad_id, e.nombre
            ) afc
            JOIN (
                SELECT entidad_id, COUNT(*) AS total_clientes_entidad
                FROM clientes WHERE estado = 'activo' GROUP BY entidad_id
            ) tot ON tot.entidad_id = afc.entidad_id
            ORDER BY afc.agricultores_afectados DESC
        """, params)
        rows = cur.fetchall()
        cur.close(); conn.close()

        if not rows:
            return jsonify({'capa': nombre, 'entidades': []})

        entidades = []
        for r in rows:
            afectados = int(r['agricultores_afectados'])
            total_ent = int(r['total_clientes_entidad'] or 1)
            entidades.append({
                'entidad_id': r['entidad_id'],
                'nombre': r['entidad_nombre'],
                'agricultores': afectados,
                'total_entidad': total_ent,
                'hectareas': round(float(r['hectareas'] or 0), 2),
                'monto': round(float(r['monto'] or 0), 2),
                'pct_damage': round(afectados / total_ent * 100, 1),
            })
        return jsonify({'capa': nombre, 'entidades': entidades})
    except Exception as e:
        logger.error("Error entidades por capa %s: %s", nombre, str(e))
        return jsonify({'error': str(e)}), 500


@capas_riesgo_bp.route('/api/capas-riesgo/<nombre>/cultivos', methods=['GET'])
def api_cultivos_por_capa(nombre):
    """Top 15 cultivos por % de clientes expuestos a la capa."""
    info = CAPAS_DISPONIBLES.get(nombre)
    if info is None:
        return jsonify({'error': f'Capa "{nombre}" no existe'}), 404
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        condiciones, params_base = _filtro_capa_extra(['r.capa = %s'], [nombre])
        where_sql = ' AND '.join(condiciones)
        cur.execute(f"""
            SELECT afc.cultivo_id, afc.cultivo_nombre, afc.agricultores_afectados,
                   afc.hectareas, afc.monto, tot.total_cultivo, dep.departamentos
            FROM (
                SELECT c.cultivo_id, tc.nombre AS cultivo_nombre,
                       COUNT(*) AS agricultores_afectados,
                       COALESCE(SUM(c.hectareas), 0) AS hectareas,
                       COALESCE(SUM(c.monto_asegurado), 0) AS monto
                FROM clientes_riesgo_capa r
                JOIN clientes c ON c.id = r.cliente_id
                LEFT JOIN tabla_cultivos tc ON tc.id = c.cultivo_id
                WHERE {where_sql}
                GROUP BY c.cultivo_id, tc.nombre
            ) afc
            JOIN (
                SELECT cultivo_id, COUNT(*) AS total_cultivo
                FROM clientes WHERE estado = 'activo' GROUP BY cultivo_id
            ) tot ON tot.cultivo_id = afc.cultivo_id
            LEFT JOIN (
                SELECT c.cultivo_id,
                       STRING_AGG(DISTINCT INITCAP(LOWER(c.departamento)), ', '
                                  ORDER BY INITCAP(LOWER(c.departamento))) AS departamentos
                FROM clientes_riesgo_capa r
                JOIN clientes c ON c.id = r.cliente_id
                WHERE {where_sql}
                GROUP BY c.cultivo_id
            ) dep ON dep.cultivo_id = afc.cultivo_id
            ORDER BY afc.agricultores_afectados DESC
            LIMIT 15
        """, params_base + params_base)
        rows = cur.fetchall()
        cur.close(); conn.close()

        cultivos = []
        for r in rows:
            afectados = int(r['agricultores_afectados'])
            total_cult = int(r['total_cultivo'] or 1)
            cultivos.append({
                'cultivo_id': r['cultivo_id'],
                'cultivo_nombre': r['cultivo_nombre'],
                'agricultores': afectados,
                'total_cultivo': total_cult,
                'hectareas': round(float(r['hectareas'] or 0), 2),
                'monto': round(float(r['monto'] or 0), 2),
                'pct_damage': round(afectados / total_cult * 100, 1),
                'departamentos': r['departamentos'] or '',
            })
        return jsonify({'capa': nombre, 'cultivos': cultivos})
    except Exception as e:
        logger.error("Error cultivos por capa %s: %s", nombre, str(e))
        return jsonify({'error': str(e)}), 500
