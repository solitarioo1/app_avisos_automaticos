"""
routes/clasificar_cliente.py - "Clasifica tu Cliente": página independiente
con 2 formas de validar exposición:

1. Excel de clientes EXTERNOS (prospectos, no están en la BD) contra UNA capa
   de riesgo elegida — ver routes/capas_riesgo.py::api_clasificar_excel,
   esta página solo sirve la UI y reutiliza ese endpoint.
2. Foto(s) georreferenciada(s) (2-3 a la vez) de una parcela: se extrae el
   GPS de la foto, se cruza contra TODAS las capas de riesgo (sin recorte
   agrícola, ver feedback_no_cruzar_capa_agraria), se muestran los siniestros
   ya reportados cerca, y queda un historial de cada consulta (trazabilidad).
"""
import logging

import psycopg2.extras
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from shapely.geometry import Point

from CONFIG.db import get_connection
from CONFIG.imagenes import validar_y_sanear, FotoInvalida
from routes.capas_riesgo import CAPAS_DISPONIBLES, _cargar_capa_preview_gdf, _nivel_estandar, _COLOR_NIVEL_ESTANDAR
from routes.evaluacion_riesgo import _siniestros_cercanos

logger = logging.getLogger(__name__)

clasificar_cliente_bp = Blueprint('clasificar_cliente', __name__, url_prefix='/clasificar-cliente')

MIN_FOTOS_VALIDACION = 1
MAX_FOTOS_VALIDACION = 3


@clasificar_cliente_bp.route('/', methods=['GET'])
@login_required
def index():
    return render_template('clasificar_cliente.html')


def _exposicion_todas_las_capas(lat, lon):
    """Cruza el punto contra TODAS las capas de riesgo disponibles (las ya
    corregidas, sin recorte agrícola) — a diferencia de evaluacion_riesgo.py
    que solo mira la(s) capa(s) ligada(s) a UN evento, acá se quiere ver TODO
    de una vez (pedido explícito: "lista... de todo los niveles de exposición
    a toda las capas")."""
    punto = Point(lon, lat)
    resultados = []
    for nombre, info in CAPAS_DISPONIBLES.items():
        gdf = _cargar_capa_preview_gdf(nombre)
        en_capa, nivel = False, None
        if gdf is not None and not gdf.empty:
            campo_cat = info.get('campo_categoria')
            match = gdf[gdf.contains(punto)]
            if not match.empty:
                en_capa = True
                valor_crudo = match.iloc[0][campo_cat] if campo_cat else None
                nivel = _nivel_estandar(nombre, valor_crudo) if campo_cat else 'Expuesto'
            elif nombre == 'rio':
                en_capa, nivel = True, 'Bajo'  # mismo criterio que el resto de la app
        resultados.append({
            'nombre': nombre, 'label': info.get('label', nombre),
            'disponible': gdf is not None,
            'en_capa': en_capa, 'nivel': nivel,
            'color': _COLOR_NIVEL_ESTANDAR.get(nivel) if nivel else None,
        })
    return resultados


@clasificar_cliente_bp.route('/api/validar-foto', methods=['POST'])
@login_required
def api_validar_foto():
    fotos = request.files.getlist('fotos')
    if not fotos:
        return jsonify({'error': 'No se recibió ninguna foto'}), 400
    if len(fotos) > MAX_FOTOS_VALIDACION:
        return jsonify({'error': f'Máximo {MAX_FOTOS_VALIDACION} fotos a la vez'}), 400

    # Ubicación manual: cuando ni EXIF ni OCR encontraron nada, el usuario
    # (interno, con login) puede mirar la foto él mismo y marcar el punto en
    # el mapa — el frontend reenvía estos campos en un segundo intento.
    lat_manual = request.form.get('lat_manual', '').strip()
    lon_manual = request.form.get('lon_manual', '').strip()

    lat = lon = None
    if lat_manual and lon_manual:
        try:
            lat_m, lon_m = float(lat_manual), float(lon_manual)
            if -19.5 <= lat_m <= 0.5 and -82.0 <= lon_m <= -68.0:
                lat, lon = lat_m, lon_m
        except ValueError:
            pass

    errores = []
    total_validas = 0
    for f in fotos:
        contenido = f.read()
        nombre_archivo = f.filename or 'foto.jpg'
        if len(contenido) > 15 * 1024 * 1024:
            errores.append(f'{nombre_archivo}: pesa más de 15MB')
            continue
        try:
            _, foto_lat, foto_lon = validar_y_sanear(contenido, nombre_archivo)
        except FotoInvalida as e:
            errores.append(str(e))
            continue
        total_validas += 1
        if lat is None and foto_lat is not None:
            lat, lon = foto_lat, foto_lon

    if errores:
        return jsonify({'error': ' | '.join(errores)}), 400
    if lat is None:
        # No se pudo ni con EXIF ni con OCR — el frontend muestra la foto y
        # deja marcar el punto manual en el mapa (reintenta con lat_manual/lon_manual).
        return jsonify({
            'error': 'No se pudo leer la ubicación automáticamente (ni GPS ni texto en la imagen)',
            'necesita_manual': True,
        }), 400

    exposicion = _exposicion_todas_las_capas(lat, lon)
    cercanos = _siniestros_cercanos(siniestro_id=-1, lat=lat, lon=lon)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO clasificar_cliente_historial (usuario, latitud, longitud, total_fotos, exposicion)
        VALUES (%s, %s, %s, %s, %s) RETURNING id, creado_en
    """, (current_user.username, lat, lon, total_validas, psycopg2.extras.Json(exposicion)))
    historial_id, creado_en = cur.fetchone()
    conn.commit()
    cur.close(); conn.close()

    return jsonify({
        'historial_id': historial_id,
        'creado_en': creado_en.isoformat(),
        'latitud': lat, 'longitud': lon,
        'total_fotos_validas': total_validas,
        'exposicion': exposicion,
        'siniestros_cercanos': cercanos,
    })


@clasificar_cliente_bp.route('/api/historial', methods=['GET'])
@login_required
def api_historial():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, usuario, latitud, longitud, total_fotos, exposicion, creado_en
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
    return jsonify({'total': len(filas), 'historial': filas})
