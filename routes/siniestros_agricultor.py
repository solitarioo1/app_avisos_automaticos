"""
routes/siniestros_agricultor.py - Formulario público (SIN login) para que el
agricultor reporte un siniestro desde su celular: datos de contacto, cultivo
afectado, evento climático y al menos 1 foto georreferenciada de su parcela.

La ubicación del siniestro sale del EXIF GPS de las fotos (no se pide GPS del
navegador ni se cruza con la tabla clientes) — si ninguna foto trae GPS, el
siniestro queda guardado sin latitud/longitud.

Las fotos se mandan a n8n (webhook) en base64, que las sube a Google Drive y
registra una fila en un Sheet — ver n8n/04siniestro_foto_drive.json.
"""
import logging
import os
import re
import base64
import requests
from datetime import datetime

from flask import Blueprint, render_template, request, jsonify

from CONFIG.db import get_connection
from CONFIG.imagenes import validar_y_sanear as _validar_y_sanear, FotoInvalida

logger = logging.getLogger(__name__)

siniestros_agricultor_bp = Blueprint('siniestros_agricultor', __name__, url_prefix='/siniestro')

EVENTOS_VALIDOS = [
    'Inundación', 'Huayco', 'Sequía', 'Helada', 'Friaje',
    'Viento Fuerte', 'Incendio Forestal', 'Otro',
]
ALCANCES_VALIDOS = ['Total', 'Parcial']
MIN_FOTOS = 1
MAX_FOTOS = 6

N8N_WEBHOOK_SINIESTRO_FOTO = os.getenv('N8N_WEBHOOK_SINIESTRO_FOTO', '')
N8N_WEBHOOK_SINIESTRO_EMAIL = os.getenv('N8N_WEBHOOK_SINIESTRO_EMAIL', '')
_REGEX_CORREO = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


@siniestros_agricultor_bp.route('/reportar', methods=['GET'])
def formulario():
    return render_template('siniestro_agricultor.html', eventos=EVENTOS_VALIDOS)


@siniestros_agricultor_bp.route('/reportar', methods=['POST'])
def guardar():
    dni = request.form.get('dni', '').strip()
    nombre_completo = request.form.get('nombre_completo', '').strip()
    celular1 = request.form.get('celular1', '').strip()
    celular2 = request.form.get('celular2', '').strip() or None
    correo = request.form.get('correo', '').strip()
    cultivo_afectado = request.form.get('cultivo_afectado', '').strip()
    alcance_dano = request.form.get('alcance_dano', '').strip()
    evento = request.form.get('evento', '').strip()
    fecha_evento = request.form.get('fecha_evento', '').strip()
    fotos = request.files.getlist('fotos')

    errores = []
    if not dni or not dni.isdigit() or len(dni) not in (8, 9):
        errores.append('DNI inválido')
    if not nombre_completo:
        errores.append('Falta el nombre completo')
    if not celular1 or len(celular1) < 9:
        errores.append('Falta el celular principal')
    if not correo or not _REGEX_CORREO.match(correo):
        errores.append('Correo electrónico inválido o faltante')
    if not cultivo_afectado:
        errores.append('Falta el cultivo afectado')
    if alcance_dano not in ALCANCES_VALIDOS:
        errores.append('Alcance del daño inválido')
    if evento not in EVENTOS_VALIDOS:
        errores.append('Evento climático inválido')
    if not fecha_evento:
        errores.append('Falta la fecha del evento')
    if len(fotos) < MIN_FOTOS:
        errores.append(f'Se requieren al menos {MIN_FOTOS} fotos')
    if len(fotos) > MAX_FOTOS:
        errores.append(f'Máximo {MAX_FOTOS} fotos')

    if errores:
        return jsonify({'status': 'error', 'errores': errores}), 400

    # Leer y validar cada foto UNA vez (se reusan para EXIF y para el envío a
    # n8n) — los archivos de Flask se "consumen" al leerlos. Cada foto pasa
    # por _validar_y_sanear: rechaza archivos que no sean imágenes reales,
    # formatos no permitidos, tamaños sospechosos, y re-codifica el píxel
    # limpio (ver docstring de la función — defensa contra uploads maliciosos
    # en un endpoint público sin login).
    fotos_data = []
    errores_fotos = []
    for f in fotos:
        contenido = f.read()
        nombre_archivo = f.filename or 'foto.jpg'
        if len(contenido) > 15 * 1024 * 1024:
            errores_fotos.append(f'{nombre_archivo}: pesa más de 15MB')
            continue
        try:
            contenido_limpio, lat, lon, _origen = _validar_y_sanear(contenido, nombre_archivo)
        except FotoInvalida as e:
            errores_fotos.append(str(e))
            continue
        if lat is None:
            errores_fotos.append(f'{nombre_archivo}: no se pudo determinar la ubicación (ni GPS ni texto en la foto), sube otra foto tomada con la cámara')
            continue
        fotos_data.append({
            'filename': nombre_archivo,
            'contenido': contenido_limpio,
            'lat': lat,
            'lon': lon,
        })

    if errores_fotos:
        return jsonify({'status': 'error', 'errores': errores_fotos}), 400
    if len(fotos_data) < MIN_FOTOS:
        return jsonify({'status': 'error', 'errores': [f'Se requieren al menos {MIN_FOTOS} fotos válidas']}), 400

    # Ubicación del siniestro: todas las fotos ya tienen GPS acá, se usa la primera.
    lat_siniestro, lon_siniestro = fotos_data[0]['lat'], fotos_data[0]['lon']

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO siniestros_agricultor
                (dni, nombre_completo, celular1, celular2, correo, cultivo_afectado,
                 alcance_dano, evento, fecha_evento, latitud, longitud)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (dni, nombre_completo, celular1, celular2, correo, cultivo_afectado,
              alcance_dano, evento, fecha_evento, lat_siniestro, lon_siniestro))
        siniestro_id = cur.fetchone()[0]

        for fd in fotos_data:
            cur.execute("""
                INSERT INTO siniestros_agricultor_fotos (siniestro_id, latitud, longitud)
                VALUES (%s,%s,%s) RETURNING id
            """, (siniestro_id, fd['lat'], fd['lon']))
            fd['foto_id'] = cur.fetchone()[0]

        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error('Error guardando siniestro: %s', str(e))
        return jsonify({'status': 'error', 'errores': ['Error guardando el reporte, intenta de nuevo']}), 500
    finally:
        cur.close()
        conn.close()

    # Disparar n8n para subir las fotos a Drive + fila en Sheet. Si n8n falla
    # o no está configurado, el siniestro YA quedó guardado en la BD — no se
    # pierde el reporte del agricultor por un problema de Drive.
    if N8N_WEBHOOK_SINIESTRO_FOTO:
        try:
            payload = {
                'siniestro_id': siniestro_id,
                'dni': dni,
                'nombre_completo': nombre_completo,
                'cultivo_afectado': cultivo_afectado,
                'evento': evento,
                'fecha_evento': fecha_evento,
                'fecha_reporte': datetime.now().isoformat(),
                'fotos': [
                    {
                        'foto_id': fd['foto_id'],
                        'filename': fd['filename'],
                        'latitud': fd['lat'],
                        'longitud': fd['lon'],
                        'base64': base64.b64encode(fd['contenido']).decode('ascii'),
                    }
                    for fd in fotos_data
                ],
            }
            requests.post(N8N_WEBHOOK_SINIESTRO_FOTO, json=payload, timeout=30)
        except Exception as e:
            logger.error('No se pudo notificar a n8n (siniestro %s ya está guardado): %s', siniestro_id, str(e))
    else:
        logger.warning('N8N_WEBHOOK_SINIESTRO_FOTO no configurado — fotos no se subieron a Drive')

    # Correo de confirmación al agricultor — flujo n8n separado (solo datos,
    # sin fotos, así no se pisa con el flujo de Drive). Si falla, el siniestro
    # ya está guardado igual, no se pierde el reporte por un problema de correo.
    if N8N_WEBHOOK_SINIESTRO_EMAIL:
        try:
            requests.post(N8N_WEBHOOK_SINIESTRO_EMAIL, json={
                'siniestro_id': siniestro_id,
                'correo': correo,
                'nombre_completo': nombre_completo,
                'dni': dni,
                'cultivo_afectado': cultivo_afectado,
                'alcance_dano': alcance_dano,
                'evento': evento,
                'fecha_evento': fecha_evento,
                'total_fotos': len(fotos_data),
                'fecha_reporte': datetime.now().isoformat(),
            }, timeout=15)
        except Exception as e:
            logger.error('No se pudo notificar a n8n para el correo (siniestro %s ya está guardado): %s', siniestro_id, str(e))
    else:
        logger.warning('N8N_WEBHOOK_SINIESTRO_EMAIL no configurado — no se envió correo de confirmación')

    return jsonify({'status': 'ok', 'siniestro_id': siniestro_id})
