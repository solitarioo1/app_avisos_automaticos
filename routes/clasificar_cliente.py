"""
routes/clasificar_cliente.py - "Evaluación de Afiliaciones" (antes "Clasifica tu
Cliente"; la URL /clasificar-cliente/ y el nombre del blueprint no cambiaron,
solo el texto visible). Agrobanco/microfinancieras comparten fotos
georreferenciadas de un prospecto en campo y La Positiva tiene que responder
con el nivel de exposición en minutos — 3 caminos, todos con la MISMA lógica
de fondo y el MISMO resultado final (tabla + mapa + exportable):

1. Excel de prospectos (no están en la BD) con coordenadas -> /api/clasificar-excel.
2. 1-3 fotos georreferenciadas de UNA parcela -> /api/validar-foto (instantáneo).
3. Lote ZIP (hasta ~100 fotos, cada una un prospecto independiente) ->
   /api/clasificar-lote + polling en /api/lote/<id>/estado. Se procesa en un
   hilo de fondo con cada ítem commiteado individualmente en BD (no en memoria)
   porque producción corre 4 workers de gunicorn — el estado tiene que
   sobrevivir a que el siguiente poll caiga en otro worker, y permite
   reintentar solo lo pendiente/fallido si el proceso se corta a la mitad.

Todas las capas de riesgo usadas son las RAW ya corregidas (sin recorte de
zona agrícola, ver feedback_no_cruzar_capa_agraria) — para Inundación y
Movimiento de Masa se usa además el archivo COMPLETO (no el preview
simplificado) vía _cargar_capa_completa_cached, para no perder precisión de
borde de polígono al dar una respuesta definitiva de afiliación.

Las fotos llegan en su gran mayoría SIN metadata EXIF (WhatsApp, capturas de
pantalla) — por eso el flujo de 1 foto permite marcar el punto a mano en el
mapa cuando ni EXIF ni OCR encuentran ubicación, y el lote tiene el mismo
mecanismo por ítem vía /api/lote/<id>/item/<id>/manual.
"""
import logging
import threading
import zipfile
from pathlib import Path
from io import BytesIO

import geopandas as gpd
import pandas as pd
import psycopg2.extras
from flask import Blueprint, render_template, request, jsonify, Response, send_file
from flask_login import login_required, current_user
from shapely.geometry import Point

from CONFIG.db import get_connection
from CONFIG.imagenes import validar_y_sanear, FotoInvalida
from routes.capas_riesgo import (
    CAPAS_DISPONIBLES, _cargar_capa_completa_cached, _nivel_estandar, _COLOR_NIVEL_ESTANDAR,
)
from routes.evaluacion_riesgo import _haversine_km, RADIO_CERCANOS_KM, _ubicar_punto

logger = logging.getLogger(__name__)

clasificar_cliente_bp = Blueprint('clasificar_cliente', __name__, url_prefix='/clasificar-cliente')

MIN_FOTOS_VALIDACION = 1
MAX_FOTOS_VALIDACION = 3
MAX_FOTOS_LOTE = 100
MAX_PESO_FOTO = 15 * 1024 * 1024  # 15MB, igual que el flujo de 1 foto
MAX_PESO_ZIP = 300 * 1024 * 1024  # 300MB, ~100 fotos de 3MB
LAT_MIN, LAT_MAX = -19.5, 0.5
LON_MIN, LON_MAX = -82.0, -68.0

BASE_DIR = Path(__file__).parent.parent
FOTOS_DIR = BASE_DIR / 'OUTPUT' / 'evaluacion_afiliaciones'


@clasificar_cliente_bp.route('/', methods=['GET'])
@login_required
def index():
    return render_template('clasificar_cliente.html')


# ============================================================================
# Evaluación compartida — la usan Excel, Foto única y Lote ZIP
# ============================================================================

def _exposicion_todas_las_capas(lat, lon, capas_filtro=None):
    """Cruza el punto contra las capas de riesgo elegidas (todas por defecto,
    las ya corregidas sin recorte agrícola). Para Inundación/Mov. Masa usa el
    archivo completo (sin simplificar) — ver _cargar_capa_completa_cached.

    Usa el índice espacial (gdf.sindex) para el contains, en vez de
    gdf.contains(punto) directo: ese último prueba el punto contra CADA
    polígono de la capa uno por uno (O(n) por punto); con sindex.query solo
    se testean los pocos candidatos cuyo bounding-box ya contiene el punto
    (R-tree, prefiltro barato) — medido con un Excel real: 10 filas pasaron
    de ~2.5s/fila a prácticamente instantáneo por fila tras este cambio.

    OJO con el predicate: sindex.query(geometria, predicate=X) evalúa
    X(geometria_input, geometria_del_arbol) — NO al revés. Para "¿el polígono
    contiene al punto?" el predicate correcto es 'within' (¿el punto está
    DENTRO del polígono?), no 'contains' (eso pregunta si el PUNTO contiene
    al polígono, imposible, siempre da 0 resultados). Se probó mal una vez
    con 'contains' y clasificó todo como "no expuesto" en todas las capas
    sin ningún error visible — verificar con un punto de nivel conocido
    (ej. Faja Marginal en Pachacamac, -12.1455/-76.8324, debe dar "Muy Alto")
    después de tocar esta función."""
    punto = Point(lon, lat)
    nombres = capas_filtro if capas_filtro else list(CAPAS_DISPONIBLES.keys())
    resultados = []
    for nombre in nombres:
        info = CAPAS_DISPONIBLES.get(nombre)
        if not info:
            continue
        gdf = _cargar_capa_completa_cached(nombre)
        en_capa, nivel = False, None
        if gdf is not None and not gdf.empty:
            campo_cat = info.get('campo_categoria')
            candidatos = gdf.iloc[gdf.sindex.query(punto, predicate='within')]
            if not candidatos.empty:
                en_capa = True
                valor_crudo = candidatos.iloc[0][campo_cat] if campo_cat else None
                nivel = _nivel_estandar(nombre, valor_crudo) if campo_cat else 'Expuesto'
            elif nombre == 'rio':
                en_capa, nivel = True, 'Bajo'  # mismo criterio que el resto de la app
        resultados.append({
            'nombre': nombre, 'label': info.get('label', nombre),
            'disponible': gdf is not None,
            'en_capa': en_capa, 'nivel': nivel,
            'color': _COLOR_NIVEL_ESTANDAR.get(nivel) if nivel else None,
            'distancia_rio_m': _distancia_al_rio(lat, lon) if nombre == 'rio' else None,
        })
    return resultados


_rios_lineas_cache = None  # GeoDataFrame de los 947 tramos "Río" (líneas, EPSG:4326), cacheado


def _huso_utm(lon):
    """Mismo criterio que CONFIG/recorte_zona_agricola.py::_huso_utm — Perú
    cae en 3 husos UTM (17S/18S/19S) según la longitud, un solo huso fijo
    distorsiona la distancia real lejos de su meridiano central."""
    if lon >= -78:
        return 32718  # UTM 18S
    if lon >= -84:
        return 32717  # UTM 17S
    return 32719      # UTM 19S


def _cargar_rios_lineas():
    """Shapefile ORIGINAL de ríos (líneas, no el buffer por bandas que usa la
    clasificación Muy Alto/Alto/Medio/Bajo) — chico (947 tramos tipo 'Río'),
    se carga una sola vez. Sirve para dar la distancia EXACTA en metros,
    complemento del nivel por banda (que no dice "cuánto" es Muy Alto)."""
    global _rios_lineas_cache
    if _rios_lineas_cache is not None:
        return _rios_lineas_cache
    ruta = BASE_DIR / 'CAPAS' / 'CAPA_RIOS_DEPARTAMENTO' / 'Rios_quebradas_ANA_geogpsperu_SuyoPomalia.shp'
    if not ruta.exists():
        _rios_lineas_cache = None
        return None
    gdf = gpd.read_file(ruta)
    gdf = gdf[gdf['TIPO_CA'] == 'Río'][['geometry']]
    if gdf.crs is None:
        gdf = gdf.set_crs('EPSG:4326')
    _rios_lineas_cache = gdf
    return gdf


def _distancia_al_rio(lat, lon):
    """Distancia en metros al tramo de río más cercano (no a la banda, al
    cauce real) — reproyecta al huso UTM correcto del punto para que la
    distancia sea métrica de verdad, no grados."""
    gdf = _cargar_rios_lineas()
    if gdf is None or gdf.empty:
        return None
    huso = _huso_utm(lon)
    punto_utm = gpd.GeoSeries([Point(lon, lat)], crs='EPSG:4326').to_crs(huso).iloc[0]
    gdf_utm = gdf.to_crs(huso)
    return round(float(gdf_utm.distance(punto_utm).min()))


def _ubicacion_admin(lat, lon):
    """Departamento/provincia/distrito del punto (None, None, None si cae
    fuera de Perú) — reusa el geocodificador inverso ya construido para
    Evaluación de Riesgo, barato (point-in-polygon en memoria, sin BD)."""
    if lat is None or lon is None:
        return {'departamento': None, 'provincia': None, 'distrito': None}
    depto, prov, dist = _ubicar_punto(lat, lon)
    return {'departamento': depto, 'provincia': prov, 'distrito': dist}


def _siniestros_cercanos_bulk(puntos, radio_km=RADIO_CERCANOS_KM):
    """Como _siniestros_cercanos (evaluacion_riesgo.py) pero para muchos puntos
    a la vez: esa función abre una conexión y hace una query POR punto — bien
    para 1 caso, caro para un Excel de cientos de filas o un lote de 100 fotos.
    Acá se carga la tabla completa UNA vez y se calculan las distancias en
    memoria. `puntos`: lista de (lat, lon) o (None, None). Devuelve una lista
    paralela de listas de siniestros cercanos.

    Dos fuentes combinadas (distinguidas por 'fuente'):
    - siniestros_agricultor: reportes nuevos vía esta app (pocos todavía).
    - siniestros_historico: las 20,866 filas 2013-2026 de Mapa de Calor de
      Siniestros — solo 8,319 tienen GPS, esas son las que entran acá. Las
      12,547 sin GPS (con departamento/provincia/distrito) NO se pueden poner
      en un radio de km; se cuentan aparte por distrito en
      _siniestros_distrito()."""
    if not puntos:
        return []
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, dni, nombre_completo, cultivo_afectado, evento, fecha_evento,
               latitud, longitud, estado
        FROM siniestros_agricultor
        WHERE latitud IS NOT NULL AND longitud IS NOT NULL
    """)
    todos = cur.fetchall()
    for s in todos:
        s['fuente'] = 'app'

    cur.execute("""
        SELECT id, cultivo, evento, fecha_evento, resultado, monto_indemnizable,
               latitud, longitud
        FROM siniestros_historico
        WHERE latitud IS NOT NULL AND longitud IS NOT NULL
    """)
    historico = cur.fetchall()
    cur.close(); conn.close()
    for s in historico:
        s['fuente'] = 'historico'
    todos += historico

    for s in todos:
        s['latitud'] = float(s['latitud'])
        s['longitud'] = float(s['longitud'])

    resultado = []
    for lat, lon in puntos:
        cercanos = []
        if lat is not None and lon is not None:
            for s in todos:
                dist = _haversine_km(lat, lon, s['latitud'], s['longitud'])
                if dist <= radio_km:
                    c = dict(s)
                    c['distancia_km'] = round(dist, 1)
                    c['fecha_evento'] = c['fecha_evento'].isoformat() if c['fecha_evento'] else None
                    cercanos.append(c)
            cercanos.sort(key=lambda c: c['distancia_km'])
        resultado.append(cercanos)
    return resultado


_historico_sin_gps_cache = None  # (depto,prov,distrito) -> conteo, cargado 1 vez


def _cargar_historico_sin_gps():
    """De las 20,866 filas de siniestros_historico, 12,547 no tienen GPS pero
    sí departamento/provincia/distrito (texto, formato MAYÚSCULAS sin tilde —
    igual que el shapefile de _ubicar_punto, verificado: 91% matchea exacto;
    el resto son códigos tipo '030201' en vez de nombre, data sucia de origen,
    se queda fuera sin forzar el match)."""
    global _historico_sin_gps_cache
    if _historico_sin_gps_cache is not None:
        return _historico_sin_gps_cache
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT departamento, provincia, distrito, resultado, COUNT(*)
        FROM siniestros_historico
        WHERE latitud IS NULL AND departamento IS NOT NULL
              AND provincia IS NOT NULL AND distrito IS NOT NULL
        GROUP BY 1, 2, 3, 4
    """)
    filas = cur.fetchall()
    cur.close(); conn.close()

    cache = {}
    for depto, prov, dist, resultado, n in filas:
        clave = (depto, prov, dist)
        d = cache.setdefault(clave, {'total': 0, 'indemnizado': 0, 'no_indemnizado': 0, 'otro': 0})
        d['total'] += n
        r = (resultado or '').strip().upper()
        if r == 'INDEMNIZADO':
            d['indemnizado'] += n
        elif r == 'NO_INDEMNIZADO':
            d['no_indemnizado'] += n
        else:
            d['otro'] += n  # desistimiento / rechazado / sin_dato / pendiente
    _historico_sin_gps_cache = cache
    return cache


def _siniestros_distrito(departamento, provincia, distrito):
    """Complemento de _siniestros_cercanos_bulk para cuando el siniestro
    histórico no tiene coordenada: cuántos hay registrados en el MISMO
    distrito del punto evaluado (sin distancia exacta, solo el conteo)."""
    if not (departamento and provincia and distrito):
        return None
    datos = _cargar_historico_sin_gps().get((departamento, provincia, distrito))
    if not datos:
        return None
    return {'departamento': departamento, 'provincia': provincia, 'distrito': distrito, **datos}


def _capas_filtro_desde_request(fuente):
    """fuente: request.form o request.args. Campo opcional 'capa' -> [capa], si
    no viene o es 'todas'/'' -> None (todas las capas)."""
    capa = (fuente.get('capa') or '').strip()
    if not capa or capa == 'todas':
        return None
    return [capa] if capa in CAPAS_DISPONIBLES else None


def _guardar_foto(subcarpeta, nombre_base, contenido_bytes):
    """Guarda la foto ya saneada (bytes re-codificados por validar_y_sanear,
    nunca el archivo crudo que subió el usuario) y devuelve la ruta relativa
    a FOTOS_DIR para guardar en BD — se sirve después vía /api/foto/<...>."""
    carpeta = FOTOS_DIR / subcarpeta
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre_seguro = "".join(c for c in nombre_base if c.isalnum() or c in "._-") or 'foto.jpg'
    if not nombre_seguro.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
        nombre_seguro += '.jpg'
    ruta = carpeta / nombre_seguro
    ruta.write_bytes(contenido_bytes)
    return f"{subcarpeta}/{nombre_seguro}"


# ============================================================================
# 1. Foto(s) georreferenciada(s) — 1 a 3, UNA sola parcela, instantáneo
# ============================================================================

@clasificar_cliente_bp.route('/api/validar-foto', methods=['POST'])
@login_required
def api_validar_foto():
    fotos = request.files.getlist('fotos')
    if not fotos:
        return jsonify({'error': 'No se recibió ninguna foto'}), 400
    if len(fotos) > MAX_FOTOS_VALIDACION:
        return jsonify({'error': f'Máximo {MAX_FOTOS_VALIDACION} fotos a la vez (para lotes más grandes usa la pestaña ZIP)'}), 400

    lat_manual = request.form.get('lat_manual', '').strip()
    lon_manual = request.form.get('lon_manual', '').strip()

    lat = lon = None
    if lat_manual and lon_manual:
        try:
            lat_m, lon_m = float(lat_manual), float(lon_manual)
            if LAT_MIN <= lat_m <= LAT_MAX and LON_MIN <= lon_m <= LON_MAX:
                lat, lon = lat_m, lon_m
        except ValueError:
            pass

    errores = []
    total_validas = 0
    ruta_foto = None
    origen_ubicacion = 'manual' if lat is not None else None
    for f in fotos:
        contenido = f.read()
        nombre_archivo = f.filename or 'foto.jpg'
        if len(contenido) > MAX_PESO_FOTO:
            errores.append(f'{nombre_archivo}: pesa más de 15MB')
            continue
        try:
            saneada, foto_lat, foto_lon, foto_origen = validar_y_sanear(contenido, nombre_archivo)
        except FotoInvalida as e:
            errores.append(str(e))
            continue
        total_validas += 1
        if ruta_foto is None:
            ruta_foto = _guardar_foto('historial_tmp', nombre_archivo, saneada)
        if lat is None and foto_lat is not None:
            lat, lon, origen_ubicacion = foto_lat, foto_lon, foto_origen

    if errores:
        return jsonify({'error': ' | '.join(errores)}), 400
    if lat is None:
        return jsonify({
            'error': 'No se pudo leer la ubicación automáticamente (ni GPS ni texto en la imagen)',
            'necesita_manual': True,
        }), 400

    capas_filtro = _capas_filtro_desde_request(request.form)
    exposicion = _exposicion_todas_las_capas(lat, lon, capas_filtro)
    cercanos = _siniestros_cercanos_bulk([(lat, lon)])[0]
    ubicacion = _ubicacion_admin(lat, lon)
    siniestros_distrito = _siniestros_distrito(ubicacion['departamento'], ubicacion['provincia'], ubicacion['distrito'])

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO clasificar_cliente_historial (usuario, latitud, longitud, total_fotos, exposicion, ruta_foto)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, creado_en
    """, (current_user.username, lat, lon, total_validas, psycopg2.extras.Json(exposicion), ruta_foto))
    historial_id, creado_en = cur.fetchone()
    conn.commit()
    cur.close(); conn.close()

    # Mover la foto a la carpeta final usando el id real del historial (se
    # guardó primero en "historial_tmp" porque recién acá se conoce el id).
    if ruta_foto:
        origen = FOTOS_DIR / ruta_foto
        destino_dir = FOTOS_DIR / 'historial' / str(historial_id)
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = destino_dir / origen.name
        try:
            origen.replace(destino)
            ruta_foto = f"historial/{historial_id}/{origen.name}"
            conn = get_connection(); cur = conn.cursor()
            cur.execute("UPDATE clasificar_cliente_historial SET ruta_foto=%s WHERE id=%s", (ruta_foto, historial_id))
            conn.commit(); cur.close(); conn.close()
        except OSError:
            pass

    return jsonify({
        'historial_id': historial_id,
        'creado_en': creado_en.isoformat(),
        'latitud': lat, 'longitud': lon,
        'origen_ubicacion': origen_ubicacion,
        'total_fotos_validas': total_validas,
        'exposicion': exposicion,
        'siniestros_cercanos': cercanos,
        'siniestros_distrito': siniestros_distrito,
        'ubicacion': ubicacion,
        'foto_url': f'/clasificar-cliente/api/foto/historial/{historial_id}' if ruta_foto else None,
    })


@clasificar_cliente_bp.route('/api/historial', methods=['GET'])
@login_required
def api_historial():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, usuario, latitud, longitud, total_fotos, exposicion, creado_en, ruta_foto
        FROM clasificar_cliente_historial
        ORDER BY creado_en DESC
        LIMIT 100
    """)
    filas = cur.fetchall()
    cur.close(); conn.close()
    for f in filas:
        f['latitud'] = float(f['latitud'])
        f['longitud'] = float(f['longitud'])
        f['creado_en'] = f['creado_en'].isoformat()
        f['foto_url'] = f'/clasificar-cliente/api/foto/historial/{f["id"]}' if f.pop('ruta_foto', None) else None
    return jsonify({'total': len(filas), 'historial': filas})


@clasificar_cliente_bp.route('/api/foto/historial/<int:historial_id>', methods=['GET'])
@login_required
def api_foto_historial(historial_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT ruta_foto FROM clasificar_cliente_historial WHERE id=%s", (historial_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row or not row[0]:
        return jsonify({'error': 'Foto no encontrada'}), 404
    ruta = FOTOS_DIR / row[0]
    if not ruta.exists():
        return jsonify({'error': 'Foto no encontrada en disco'}), 404
    return send_file(ruta)


# ============================================================================
# 2. Excel de prospectos — procesa y devuelve JSON (antes: descarga directa)
# ============================================================================

_COLS_LAT_EXCEL = ['lat', 'latitud', 'latitude']
_COLS_LON_EXCEL = ['lon', 'lng', 'longitud', 'longitude']


@clasificar_cliente_bp.route('/api/clasificar-excel', methods=['POST'])
@login_required
def api_clasificar_excel():
    """Excel de prospectos (no están en la BD) con coordenadas -> evalúa cada
    fila contra las capas elegidas (todas por defecto) + siniestros cercanos,
    devuelve JSON para pintar tabla+mapa (igual que Foto/Lote). La descarga en
    Excel la arma por separado /api/exportar-resultados, con lo que ya se
    calculó acá — no se vuelve a procesar."""
    archivo = request.files.get('excel')
    if not archivo:
        return jsonify({'error': 'No se recibió ningún archivo'}), 400
    try:
        df = pd.read_excel(archivo)
    except Exception as e:
        logger.error("Error leyendo Excel a clasificar: %s", str(e))
        return jsonify({'error': 'No se pudo leer el Excel (¿formato .xlsx válido?)'}), 400

    columnas_lower = {str(c).strip().lower(): c for c in df.columns}

    def _detectar(candidatos):
        for c in candidatos:
            if c in columnas_lower:
                return columnas_lower[c]
        return None

    col_lat = _detectar(_COLS_LAT_EXCEL)
    col_lon = _detectar(_COLS_LON_EXCEL)
    if not col_lat or not col_lon:
        return jsonify({'error': 'El Excel debe tener columnas de coordenadas: lat/latitud y lon/longitud.'}), 400

    capas_filtro = _capas_filtro_desde_request(request.form)

    puntos = []
    resultados = []
    for _, fila in df.iterrows():
        extra = {k: (None if pd.isna(v) else v) for k, v in fila.to_dict().items()}
        lat = lon = None
        motivo = None
        valor_lat, valor_lon = fila.get(col_lat), fila.get(col_lon)
        if pd.isna(valor_lat) or pd.isna(valor_lon) or str(valor_lat).strip() == '' or str(valor_lon).strip() == '':
            motivo = 'Sin coordenadas'
        else:
            try:
                lat, lon = float(valor_lat), float(valor_lon)
            except (TypeError, ValueError):
                motivo = 'Coordenada no numérica'
            else:
                if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
                    motivo = 'Coordenada fuera del Perú (revisar lat/lon)'
                    lat = lon = None
        puntos.append((lat, lon))
        ubicacion = _ubicacion_admin(lat, lon)
        resultados.append({
            'origen': 'excel', 'extra': extra,
            'latitud': lat, 'longitud': lon,
            'exposicion': [], 'siniestros_cercanos': [],
            'siniestros_distrito': _siniestros_distrito(ubicacion['departamento'], ubicacion['provincia'], ubicacion['distrito']),
            'ubicacion': ubicacion,
            'error': motivo,
        })

    cercanos_todos = _siniestros_cercanos_bulk(puntos)
    for r, (lat, lon), cercanos in zip(resultados, puntos, cercanos_todos):
        if r['error']:
            continue
        r['exposicion'] = _exposicion_todas_las_capas(lat, lon, capas_filtro)
        r['siniestros_cercanos'] = cercanos

    return jsonify({'total': len(resultados), 'resultados': resultados})


# ============================================================================
# 3. Lote ZIP — hasta ~100 fotos, cada una un prospecto independiente
# ============================================================================

_EXTENSIONES_IMAGEN = {'.jpg', '.jpeg', '.png', '.webp', '.heif', '.heic'}


def _procesar_lote(lote_id, archivos, capas_filtro):
    """Corre en un hilo de fondo (daemon). Procesa cada foto en secuencia y
    hace COMMIT por ítem — si el proceso se cae a la mitad, lo ya hecho queda
    guardado y /reintentar solo retoma lo pendiente/error, no todo de nuevo."""
    for nombre_archivo, contenido in archivos:
        conn = get_connection()
        cur = conn.cursor()
        try:
            if len(contenido) > MAX_PESO_FOTO:
                raise FotoInvalida('pesa más de 15MB')
            saneada, lat, lon, origen = validar_y_sanear(contenido, nombre_archivo)
            ruta_foto = _guardar_foto(f'lote_{lote_id}', nombre_archivo, saneada)
            if lat is None:
                cur.execute("""
                    UPDATE clasificar_cliente_lote_item
                    SET estado='error', error_msg=%s, ruta_foto=%s, procesado_en=NOW()
                    WHERE lote_id=%s AND nombre_archivo=%s AND estado='pendiente'
                """, ('No se pudo leer la ubicación (ni GPS, ni texto en la imagen, ni IA) — márcala a mano',
                      ruta_foto, lote_id, nombre_archivo))
            else:
                exposicion = _exposicion_todas_las_capas(lat, lon, capas_filtro)
                cercanos = _siniestros_cercanos_bulk([(lat, lon)])[0]
                cur.execute("""
                    UPDATE clasificar_cliente_lote_item
                    SET estado='ok', latitud=%s, longitud=%s, exposicion=%s,
                        siniestros_cercanos=%s, ruta_foto=%s, origen_ubicacion=%s, procesado_en=NOW()
                    WHERE lote_id=%s AND nombre_archivo=%s AND estado='pendiente'
                """, (lat, lon, psycopg2.extras.Json(exposicion), psycopg2.extras.Json(cercanos),
                      ruta_foto, origen, lote_id, nombre_archivo))
        except Exception as e:
            cur.execute("""
                UPDATE clasificar_cliente_lote_item
                SET estado='error', error_msg=%s, procesado_en=NOW()
                WHERE lote_id=%s AND nombre_archivo=%s AND estado='pendiente'
            """, (str(e), lote_id, nombre_archivo))
        cur.execute("""
            UPDATE clasificar_cliente_lote SET procesados = procesados + 1 WHERE id=%s
        """, (lote_id,))
        conn.commit()
        cur.close(); conn.close()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE clasificar_cliente_lote SET estado='completo' WHERE id=%s", (lote_id,))
    conn.commit()
    cur.close(); conn.close()
    logger.info('Lote %s terminado', lote_id)


@clasificar_cliente_bp.route('/api/clasificar-lote', methods=['POST'])
@login_required
def api_clasificar_lote():
    """Lote de fotos (4 a 100, cada una un prospecto independiente) — acepta
    o un .zip (`zip`) o fotos sueltas (`fotos`, multipart múltiple); el
    frontend fusiona ambos en una sola pestaña "Fotos", esto es lo que
    distingue cuál llegó. Si viene `lote_id` en el form, es un REINTENTO del
    mismo lote (el navegador reenvía los mismos archivos que ya tenía en
    memoria): los ítems que ya están en 'ok' se dejan intactos, solo se
    reprocesan los 'pendiente'/'error'."""
    zip_file = request.files.get('zip')
    fotos_sueltas = request.files.getlist('fotos')

    archivos = []
    if zip_file:
        contenido_zip = zip_file.read()
        if len(contenido_zip) > MAX_PESO_ZIP:
            return jsonify({'error': 'El .zip pesa más de 300MB'}), 400
        try:
            zf = zipfile.ZipFile(BytesIO(contenido_zip))
        except zipfile.BadZipFile:
            return jsonify({'error': 'El archivo no es un .zip válido'}), 400
        for info in zf.infolist():
            if info.is_dir():
                continue
            nombre = info.filename.rsplit('/', 1)[-1]
            if '.' not in nombre or f'.{nombre.rsplit(".", 1)[-1].lower()}' not in _EXTENSIONES_IMAGEN:
                continue
            archivos.append((nombre, zf.read(info)))
    elif fotos_sueltas:
        archivos = [(f.filename or 'foto.jpg', f.read()) for f in fotos_sueltas]
    else:
        return jsonify({'error': 'No se recibió ningún archivo (.zip o fotos)'}), 400

    if not archivos:
        return jsonify({'error': 'No se encontraron imágenes válidas (jpg/jpeg/png/webp/heif/heic)'}), 400
    if len(archivos) > MAX_FOTOS_LOTE:
        return jsonify({'error': f'Se recibieron {len(archivos)} fotos, máximo {MAX_FOTOS_LOTE} por lote'}), 400

    lote_id_reintento = request.form.get('lote_id', '').strip()
    conn = get_connection()
    cur = conn.cursor()

    if lote_id_reintento:
        lote_id = int(lote_id_reintento)
        cur.execute("SELECT capa_filtro FROM clasificar_cliente_lote WHERE id=%s", (lote_id,))
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close()
            return jsonify({'error': 'Lote no existe'}), 404
        capa_filtro_db = row[0]
        capas_filtro = [capa_filtro_db] if capa_filtro_db else None

        cur.execute("SELECT nombre_archivo, estado FROM clasificar_cliente_lote_item WHERE lote_id=%s", (lote_id,))
        ya_existe = {r[0]: r[1] for r in cur.fetchall()}
        a_reprocesar = [(n, c) for n, c in archivos if ya_existe.get(n) != 'ok']
        if not a_reprocesar:
            cur.close(); conn.close()
            return jsonify({'error': 'Todos los ítems de este lote ya están OK'}), 400

        for nombre, _ in a_reprocesar:
            if nombre in ya_existe:
                cur.execute("""
                    UPDATE clasificar_cliente_lote_item SET estado='pendiente', error_msg=NULL
                    WHERE lote_id=%s AND nombre_archivo=%s
                """, (lote_id, nombre))
            else:
                cur.execute("""
                    INSERT INTO clasificar_cliente_lote_item (lote_id, nombre_archivo) VALUES (%s, %s)
                """, (lote_id, nombre))
        cur.execute("""
            UPDATE clasificar_cliente_lote
            SET estado='procesando', total = total + %s
            WHERE id=%s
        """, (sum(1 for n, _ in a_reprocesar if n not in ya_existe), lote_id))
        conn.commit()
        cur.close(); conn.close()

        threading.Thread(target=_procesar_lote, args=(lote_id, a_reprocesar, capas_filtro), daemon=True).start()
        return jsonify({'lote_id': lote_id, 'total': len(a_reprocesar), 'reintento': True})

    capas_filtro = _capas_filtro_desde_request(request.form)
    capa_filtro_db = capas_filtro[0] if capas_filtro else None

    cur.execute("""
        INSERT INTO clasificar_cliente_lote (usuario, capa_filtro, total)
        VALUES (%s, %s, %s) RETURNING id
    """, (current_user.username, capa_filtro_db, len(archivos)))
    lote_id = cur.fetchone()[0]
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO clasificar_cliente_lote_item (lote_id, nombre_archivo) VALUES %s",
        [(lote_id, nombre) for nombre, _ in archivos],
    )
    conn.commit()
    cur.close(); conn.close()

    threading.Thread(target=_procesar_lote, args=(lote_id, archivos, capas_filtro), daemon=True).start()

    return jsonify({'lote_id': lote_id, 'total': len(archivos)})


def _item_a_resultado(it):
    lat = float(it['latitud']) if it['latitud'] is not None else None
    lon = float(it['longitud']) if it['longitud'] is not None else None
    ubicacion = _ubicacion_admin(lat, lon)
    return {
        'id': it['id'], 'origen': 'lote', 'extra': {'archivo': it['nombre_archivo']},
        'estado': it['estado'],
        'latitud': lat, 'longitud': lon,
        'origen_ubicacion': it.get('origen_ubicacion'),
        'exposicion': it['exposicion'] or [],
        'siniestros_cercanos': it['siniestros_cercanos'] or [],
        'siniestros_distrito': _siniestros_distrito(ubicacion['departamento'], ubicacion['provincia'], ubicacion['distrito']),
        'ubicacion': ubicacion,
        'error': it['error_msg'],
        'foto_url': f'/clasificar-cliente/api/foto/lote-item/{it["id"]}' if it.get('ruta_foto') else None,
    }


@clasificar_cliente_bp.route('/api/lote/<int:lote_id>/estado', methods=['GET'])
@login_required
def api_lote_estado(lote_id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, estado, total, procesados FROM clasificar_cliente_lote WHERE id=%s", (lote_id,))
    lote = cur.fetchone()
    if not lote:
        cur.close(); conn.close()
        return jsonify({'error': 'Lote no existe'}), 404

    cur.execute("""
        SELECT id, nombre_archivo, estado, latitud, longitud, exposicion, siniestros_cercanos, error_msg, ruta_foto, origen_ubicacion
        FROM clasificar_cliente_lote_item WHERE lote_id=%s ORDER BY id
    """, (lote_id,))
    items = cur.fetchall()
    cur.close(); conn.close()

    return jsonify({
        'lote_id': lote['id'], 'estado': lote['estado'],
        'total': lote['total'], 'procesados': lote['procesados'],
        'resultados': [_item_a_resultado(it) for it in items],
    })


@clasificar_cliente_bp.route('/api/lote/<int:lote_id>/item/<int:item_id>/manual', methods=['POST'])
@login_required
def api_lote_item_manual(lote_id, item_id):
    """Para fotos sin GPS ni OCR (la mayoría de las que llegan de campo): el
    usuario marca el punto a mano en el mapa, acá se recalcula exposición +
    siniestros cercanos para ESE ítem puntual y queda como 'ok'."""
    body = request.get_json(silent=True) or {}
    try:
        lat, lon = float(body.get('lat')), float(body.get('lon'))
    except (TypeError, ValueError):
        return jsonify({'error': 'lat/lon inválidos'}), 400
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return jsonify({'error': 'Coordenada fuera del Perú'}), 400

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT capa_filtro FROM clasificar_cliente_lote WHERE id=%s", (lote_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return jsonify({'error': 'Lote no existe'}), 404
    capas_filtro = [row[0]] if row[0] else None

    exposicion = _exposicion_todas_las_capas(lat, lon, capas_filtro)
    cercanos = _siniestros_cercanos_bulk([(lat, lon)])[0]
    cur.execute("""
        UPDATE clasificar_cliente_lote_item
        SET estado='ok', latitud=%s, longitud=%s, exposicion=%s, siniestros_cercanos=%s,
            origen_ubicacion='manual', error_msg=NULL, procesado_en=NOW()
        WHERE id=%s AND lote_id=%s
        RETURNING id, nombre_archivo, estado, latitud, longitud, exposicion, siniestros_cercanos, error_msg, ruta_foto, origen_ubicacion
    """, (lat, lon, psycopg2.extras.Json(exposicion), psycopg2.extras.Json(cercanos), item_id, lote_id))
    actualizado = cur.fetchone()
    if not actualizado:
        conn.rollback(); cur.close(); conn.close()
        return jsonify({'error': 'Ítem no existe en este lote'}), 404
    conn.commit()
    cur.close(); conn.close()

    cols = ['id', 'nombre_archivo', 'estado', 'latitud', 'longitud', 'exposicion', 'siniestros_cercanos', 'error_msg', 'ruta_foto', 'origen_ubicacion']
    it = dict(zip(cols, actualizado))
    return jsonify({'resultado': _item_a_resultado(it)})


@clasificar_cliente_bp.route('/api/foto/lote-item/<int:item_id>', methods=['GET'])
@login_required
def api_foto_lote_item(item_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT ruta_foto FROM clasificar_cliente_lote_item WHERE id=%s", (item_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row or not row[0]:
        return jsonify({'error': 'Foto no encontrada'}), 404
    ruta = FOTOS_DIR / row[0]
    if not ruta.exists():
        return jsonify({'error': 'Foto no encontrada en disco'}), 404
    return send_file(ruta)


# ============================================================================
# Exportar — un solo endpoint para Excel, Foto única y Lote (recibe el JSON
# de resultados que el frontend ya tiene en memoria, no recalcula nada)
# ============================================================================

@clasificar_cliente_bp.route('/api/exportar-resultados', methods=['POST'])
@login_required
def api_exportar_resultados():
    body = request.get_json(silent=True) or {}
    resultados = body.get('resultados') or []
    if not resultados:
        return jsonify({'error': 'No hay resultados para exportar'}), 400

    filas = []
    for r in resultados:
        fila = dict(r.get('extra') or {})
        fila['Latitud'] = r.get('latitud')
        fila['Longitud'] = r.get('longitud')
        fila['Ubicación obtenida por'] = {
            'exif': 'GPS de la foto', 'ocr': 'Texto en la foto', 'ia': 'IA (respaldo)', 'manual': 'Manual',
        }.get(r.get('origen_ubicacion'), '')
        ubicacion = r.get('ubicacion') or {}
        fila['Departamento'] = ubicacion.get('departamento')
        fila['Provincia'] = ubicacion.get('provincia')
        fila['Distrito'] = ubicacion.get('distrito')
        if r.get('error'):
            fila['Error'] = r['error']
        for exp in (r.get('exposicion') or []):
            fila[f"Nivel ({exp.get('label')})"] = exp.get('nivel') or ('Fuera de zona' if exp.get('disponible') else 'Capa no disponible')
            if exp.get('distancia_rio_m') is not None:
                fila['Distancia al río (m)'] = exp['distancia_rio_m']
        fila['Siniestros cercanos (5km)'] = len(r.get('siniestros_cercanos') or [])
        dist = r.get('siniestros_distrito')
        fila['Siniestros históricos en el distrito'] = dist['total'] if dist else 0
        filas.append(fila)

    df = pd.DataFrame(filas)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Resultados', index=False)
    buf.seek(0)

    resp = Response(buf.read(), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp.headers['Content-Disposition'] = 'attachment; filename="evaluacion_afiliaciones.xlsx"'
    return resp
