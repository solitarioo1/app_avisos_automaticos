# ============================================================================
# routes/mensajeria.py - La Positiva AgroSeguros
# Rutas Flask para módulo de mensajería WhatsApp via n8n + Google Sheets
# ============================================================================

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
import gspread
from google.oauth2.service_account import Credentials
import requests
import os
import json
import base64
from datetime import datetime

mensajeria_bp = Blueprint('mensajeria', __name__, url_prefix='/mensajeria')

# ── Configuración Google Sheets ──
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',  # Solo lectura
    'https://www.googleapis.com/auth/drive.readonly'
]
CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_JSON', 'credentials.json')
SHEET_ID         = os.getenv('MENSAJERIA_SHEET_ID', '')

# ── Webhooks n8n (desde .env) ──
WEBHOOKS = {
    'afiliaciones':    os.getenv('N8N_WEBHOOK_AFILIACIONES', ''),
    'resultados':      os.getenv('N8N_WEBHOOK_RESULTADOS', ''),
    'indemnizaciones': os.getenv('N8N_WEBHOOK_INDEMNIZACIONES', ''),
    'alertas':         os.getenv('N8N_WEBHOOK_ALERTAS', ''),
}

# ── Mapeo tipo → nombre de hoja en Google Sheets ──
HOJAS = {
    'afiliaciones':    'afiliaciones',
    'resultados':      'resultados',
    'indemnizaciones': 'indemnizaciones',
    'alertas':         'alertas',
}


def get_sheet_client():
    """Retorna cliente autenticado de gspread.
    Soporta dos métodos:
    - GOOGLE_CREDENTIALS_B64: contenido del JSON en base64 (EasyPanel/producción)
    - GOOGLE_CREDENTIALS_JSON: ruta al archivo .json (desarrollo local)
    """
    b64 = os.getenv('GOOGLE_CREDENTIALS_B64', '')
    if b64:
        # Producción: decodificar desde variable de entorno
        info = json.loads(base64.b64decode(b64).decode('utf-8'))
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        # Desarrollo local: leer desde archivo
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def get_worksheet(tipo):
    """Retorna el worksheet del tipo indicado."""
    client = get_sheet_client()
    spreadsheet = client.open_by_key(SHEET_ID)
    return spreadsheet.worksheet(HOJAS[tipo])


# ============================================================================
# PÁGINA PRINCIPAL
# ============================================================================

@mensajeria_bp.route('/')
@login_required
def index():
    """Renderiza la página de mensajería con los webhooks configurados."""
    # Pasar solo booleanos al frontend (no exponer URLs de webhook)
    config = {
        'afiliaciones':    bool(WEBHOOKS.get('afiliaciones')),
        'resultados':      bool(WEBHOOKS.get('resultados')),
        'indemnizaciones': bool(WEBHOOKS.get('indemnizaciones')),
        'alertas':         bool(WEBHOOKS.get('alertas')),
    }
    return render_template('mensajeria.html', config=config)


# ============================================================================
# ENVÍO - Llama al webhook n8n
# ============================================================================

@mensajeria_bp.route('/enviar', methods=['POST'])
def enviar():
    """
    Dispara el webhook n8n del tipo indicado.
    n8n procesa los registros pendientes, envía WhatsApp y actualiza el Sheet.
    Flask espera la respuesta de n8n con el resumen.
    """
    data = request.get_json()
    tipo = data.get('tipo', '').lower()

    if tipo not in WEBHOOKS:
        return jsonify({'success': False, 'mensaje': 'Tipo de mensaje no válido.'}), 400

    webhook_url = WEBHOOKS[tipo]
    if not webhook_url:
        return jsonify({'success': False, 'mensaje': f'Webhook de "{tipo}" no configurado en .env'}), 500

    try:
        # Llamar al webhook n8n (espera respuesta con resumen)
        resp = requests.post(
            webhook_url,
            json={'tipo': tipo},
            timeout=120  # n8n puede tardar si hay muchos mensajes
        )
        resp.raise_for_status()
        n8n_data = resp.json()

        # n8n debe retornar: { enviados, fallidos, pendientes, total, hora }
        hora_actual = datetime.now().strftime('%H:%M')
        return jsonify({
            'success':   True,
            'enviados':  n8n_data.get('enviados', 0),
            'fallidos':  n8n_data.get('fallidos', 0),
            'pendientes': n8n_data.get('pendientes', 0),
            'total':     n8n_data.get('total', 0),
            'hora':      n8n_data.get('hora', hora_actual),
            'tipo':      tipo
        })

    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'mensaje': 'El webhook de n8n tardó demasiado (timeout).'}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({'success': False, 'mensaje': f'Error al llamar webhook: {str(e)}'}), 502
    except Exception as e:
        return jsonify({'success': False, 'mensaje': f'Error inesperado: {str(e)}'}), 500


# ============================================================================
# HISTORIAL - Lee todas las hojas de Google Sheets
# ============================================================================

@mensajeria_bp.route('/historial')
def historial():
    """
    Lee las 4 hojas del Google Sheet y retorna todos los registros
    con su estado (pendiente / enviado / fallido).
    IMPORTANTE: Sin caché - siempre lee datos frescos de Google Sheets
    """
    try:
        client       = get_sheet_client()
        spreadsheet  = client.open_by_key(SHEET_ID)
        todos        = []

        for tipo, nombre_hoja in HOJAS.items():
            try:
                ws      = spreadsheet.worksheet(nombre_hoja)
                records = ws.get_all_records()  # Lee encabezados como keys
                for r in records:
                    todos.append({
                        'tipo':       tipo,
                        'nombre':     r.get('nombre', ''),
                        'numero':     r.get('numero', ''),
                        'entidad':    r.get('entidad', ''),
                        'estado':     str(r.get('estado', 'pendiente')).lower(),
                        'fecha_envio': r.get('fecha_envio', ''),
                        'mensaje':    r.get('asunto', '')[:80] + '...' if r.get('asunto', '') else ''
                    })
            except gspread.exceptions.WorksheetNotFound:
                continue

        response = jsonify({'success': True, 'registros': todos, 'total': len(todos)})
        # Deshabilitar caché - siempre datos frescos
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    except Exception as e:
        return jsonify({'success': False, 'mensaje': f'Error al leer Google Sheets: {str(e)}'}), 500