"""
routes/difusion.py — Módulo de difusión de avisos SENAMHI
Gestiona: clientes, generación de mensajes (n8n), preview y envío.
"""
import csv
import io
import logging
import os

import psycopg2
import psycopg2.extras
import requests
from flask import Blueprint, jsonify, render_template, request, Response
from flask_login import login_required

from CONFIG.db import get_connection

logger = logging.getLogger(__name__)

difusion_bp = Blueprint("difusion", __name__, url_prefix="")

# ---------------------------------------------------------------------------
# Helper de conexión (mismo patrón que decisiones.py)
# ---------------------------------------------------------------------------

def get_db_connection():
    try:
        return get_connection()
    except psycopg2.Error as e:
        logger.error("Error conexión BD: %s", str(e))
        return None


# ---------------------------------------------------------------------------
# Página principal
# ---------------------------------------------------------------------------

@difusion_bp.route("/difusion")
@login_required
def difusion_page():
    return render_template("difusion.html")


# ---------------------------------------------------------------------------
# API: estadísticas de clientes por aviso (sidebar)
# ---------------------------------------------------------------------------

@difusion_bp.route("/api/difusion/clientes/<int:numero_aviso>")
def clientes_por_aviso(numero_aviso):
    """
    Devuelve totales de clientes segmentados por nivel para el sidebar.
    También indica cuántos ya tienen mensajes generados.
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "error": "Sin conexión a BD"}), 500

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Totales por nivel (todos los clientes vinculados al aviso)
            cur.execute(
                """
                SELECT
                    nivel,
                    COUNT(*) AS total,
                    SUM(CASE WHEN correo IS NOT NULL AND correo <> '' THEN 1 ELSE 0 END) AS con_email,
                    SUM(CASE WHEN telefono IS NOT NULL AND telefono <> '' THEN 1 ELSE 0 END) AS con_telefono
                FROM clientes_por_aviso cpa
                JOIN clientes c ON c.id = cpa.cliente_id
                WHERE cpa.numero_aviso = %s
                GROUP BY nivel
                ORDER BY
                    CASE nivel
                        WHEN 'Rojo'     THEN 1
                        WHEN 'Naranja'  THEN 2
                        WHEN 'Amarillo' THEN 3
                        WHEN 'Verde'    THEN 4
                        ELSE 5
                    END
                """,
                (numero_aviso,),
            )
            niveles = cur.fetchall()

            # Total general
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM clientes_por_aviso
                WHERE numero_aviso = %s
                """,
                (numero_aviso,),
            )
            total_row = cur.fetchone()
            total_clientes = total_row["total"] if total_row else 0

            # Mensajes ya generados (estado != 'sin_mensaje')
            cur.execute(
                """
                SELECT canal_enviado, COUNT(*) AS total
                FROM clientes_envios
                WHERE numero_aviso = %s
                GROUP BY canal_enviado
                """,
                (numero_aviso,),
            )
            canales_generados = {r["canal_enviado"]: r["total"] for r in cur.fetchall()}

        return jsonify(
            {
                "success": True,
                "numero_aviso": numero_aviso,
                "total_clientes": total_clientes,
                "por_nivel": [dict(r) for r in niveles],
                "mensajes_generados": canales_generados,
            }
        )
    except psycopg2.Error as e:
        logger.error("Error clientes_por_aviso: %s", str(e))
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API: exportar clientes SMS como CSV
# ---------------------------------------------------------------------------

@difusion_bp.route("/api/difusion/clientes/export/<int:numero_aviso>")
def exportar_clientes_csv(numero_aviso):
    """Descarga CSV con clientes (canal sms) para el aviso indicado."""
    nivel = request.args.get("nivel", None)
    entidad = request.args.get("entidad", None)

    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "error": "Sin conexión a BD"}), 500

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            params = [numero_aviso]
            filtros = ""
            if nivel:
                filtros += " AND cpa.nivel = %s"
                params.append(nivel)
            if entidad:
                filtros += " AND e.nombre = %s"
                params.append(entidad)

            cur.execute(
                f"""
                SELECT
                    c.id,
                    c.nombre,
                    c.apellido,
                    c.telefono,
                    c.correo,
                    c.departamento,
                    cpa.nivel
                FROM clientes_por_aviso cpa
                JOIN clientes c ON c.id = cpa.cliente_id
                LEFT JOIN entidades e ON e.id = c.entidad_id
                WHERE cpa.numero_aviso = %s
                  AND c.telefono IS NOT NULL
                  AND c.telefono <> ''
                  {filtros}
                ORDER BY cpa.nivel, c.apellido, c.nombre
                """,
                params,
            )
            filas = cur.fetchall()

        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["id", "nombre", "apellido", "telefono", "correo", "departamento", "nivel"],
        )
        writer.writeheader()
        writer.writerows([dict(f) for f in filas])

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=clientes_sms_aviso_{numero_aviso}.csv"},
        )
    except psycopg2.Error as e:
        logger.error("Error exportar CSV: %s", str(e))
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API: marcar como enviado por SMS tras exportar CSV
# ---------------------------------------------------------------------------

@difusion_bp.route("/api/difusion/marcar_enviado_sms/<int:numero_aviso>", methods=["POST"])
def marcar_enviado_sms(numero_aviso):
    """Marca registros de clientes_envios con canal=sms como enviados."""
    data    = request.get_json(silent=True) or {}
    nivel   = data.get("nivel")
    entidad = data.get("entidad")

    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "error": "Sin conexión a BD"}), 500

    try:
        with conn.cursor() as cur:
            params  = [numero_aviso, "sms"]
            filtros = ""
            if nivel and nivel != "todos":
                filtros += " AND nivel_filtro = %s"
                params.append(nivel)
            if entidad:
                filtros += " AND entidad_filtro = %s"
                params.append(entidad)

            cur.execute(
                f"""
                UPDATE clientes_envios
                   SET estado = 'enviado', fecha_envio = NOW()
                 WHERE numero_aviso = %s
                   AND canal_enviado = %s
                   {filtros}
                """,
                params,
            )
            marcados = cur.rowcount
            conn.commit()
        return jsonify({"success": True, "marcados": marcados})
    except psycopg2.Error as e:
        conn.rollback()
        logger.error("Error marcar enviado SMS: %s", str(e))
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API: generar mensajes → llama webhook n8n
# ---------------------------------------------------------------------------

@difusion_bp.route("/api/difusion/generar", methods=["POST"])
def generar_mensajes():
    """
    Dispara el webhook n8n para que genere los mensajes y los almacene
    en clientes_envios. Flask sólo envía los parámetros de filtro.

    Body JSON esperado:
    {
        "numero_aviso": 44,
        "canal": "whatsapp",          # o "email" o "ambos"
        "nivel": "Rojo",              # opcional
        "entidad": "AGROBANCO"        # opcional
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "JSON body requerido"}), 400

    numero_aviso = data.get("numero_aviso")
    canal = data.get("canal", "ambos")
    nivel = data.get("nivel", None)
    entidades = data.get("entidades", None)          # lista de entidades (puede ser None)
    incluir_mapa = data.get("incluir_mapa", True)
    partir_mensajes = data.get("partir_mensajes", False)
    msgs_por_bloque = data.get("msgs_por_bloque", None)
    intervalo_bloques = data.get("intervalo_bloques", None)
    programar_envio = data.get("programar_envio", None)

    if not numero_aviso:
        return jsonify({"success": False, "error": "numero_aviso requerido"}), 400

    webhook_url = os.getenv("N8N_WEBHOOK_GENERAR")
    if not webhook_url:
        return jsonify({"success": False, "error": "N8N_WEBHOOK_GENERAR no configurado"}), 500

    payload = {
        "numero_aviso":    numero_aviso,
        "canal":           canal,
        "nivel":           nivel,
        "entidades":       entidades,
        "incluir_mapa":    incluir_mapa,
        "partir_mensajes": partir_mensajes,
        "msgs_por_bloque": msgs_por_bloque,
        "intervalo_bloques": intervalo_bloques,
        "programar_envio": programar_envio,
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=30)
        resp.raise_for_status()
        return jsonify(
            {
                "success": True,
                "message": "Solicitud enviada a n8n para generar mensajes",
                "n8n_status": resp.status_code,
                "payload": payload,
            }
        )
    except requests.exceptions.Timeout:
        return jsonify({"success": False, "error": "Timeout al contactar n8n"}), 504
    except requests.exceptions.RequestException as e:
        logger.error("Error webhook generar: %s", str(e))
        return jsonify({"success": False, "error": str(e)}), 502


# ---------------------------------------------------------------------------
# API: preview — 4 mensajes de muestra desde clientes_envios
# ---------------------------------------------------------------------------

@difusion_bp.route("/api/difusion/preview/<int:numero_aviso>")
def preview_mensajes(numero_aviso):
    """
    Devuelve hasta 4 registros (máximo 1 por canal×nivel) como muestra
    del message_text generado por n8n y almacenado en clientes_envios.
    """
    canal = request.args.get("canal", None)
    nivel = request.args.get("nivel", None)

    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "error": "Sin conexión a BD"}), 500

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            params = [numero_aviso]
            filtro_canal = ""
            filtro_nivel = ""
            if canal:
                filtro_canal = " AND ce.canal_enviado = %s"
                params.append(canal)
            if nivel:
                filtro_nivel = " AND ce.nivel_filtro = %s"
                params.append(nivel)

            cur.execute(
                f"""
                SELECT DISTINCT ON (ce.canal_enviado, ce.nivel_filtro)
                    ce.id,
                    ce.canal_enviado,
                    ce.nivel_filtro,
                    ce.mensaje_texto,
                    ce.estado,
                    c.nombre,
                    c.apellido,
                    c.telefono,
                    c.correo
                FROM clientes_envios ce
                JOIN clientes c ON c.id = ce.cliente_id
                WHERE ce.numero_aviso = %s
                  AND ce.mensaje_texto IS NOT NULL
                  {filtro_canal}
                  {filtro_nivel}
                ORDER BY ce.canal_enviado, ce.nivel_filtro, ce.id
                LIMIT 4
                """,
                params,
            )
            muestras = cur.fetchall()

            # Conteo general de mensajes generados
            cur.execute(
                """
                SELECT canal_enviado, estado, COUNT(*) AS total
                FROM clientes_envios
                WHERE numero_aviso = %s
                GROUP BY canal_enviado, estado
                """,
                (numero_aviso,),
            )
            resumen = cur.fetchall()

        return jsonify(
            {
                "success": True,
                "numero_aviso": numero_aviso,
                "muestras": [dict(r) for r in muestras],
                "resumen": [dict(r) for r in resumen],
                "total_muestras": len(muestras),
            }
        )
    except psycopg2.Error as e:
        logger.error("Error preview: %s", str(e))
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API: enviar — dispara webhook n8n de envío
# ---------------------------------------------------------------------------

@difusion_bp.route("/api/difusion/enviar/<int:numero_aviso>", methods=["POST"])
def enviar_mensajes(numero_aviso):
    """
    Dispara los webhooks de envío en n8n (WA y/o email según canal).
    Body JSON opcional:
    { "canal": "whatsapp" }   → sólo WhatsApp
    { "canal": "email" }      → sólo email
    { "canal": "ambos" }      → ambos (default)
    """
    data = request.get_json() or {}
    canal = data.get("canal", "ambos")

    webhook_wa    = os.getenv("N8N_WEBHOOK_ENVIAR_WA")
    webhook_sms   = os.getenv("N8N_WEBHOOK_ENVIAR_SMS")
    webhook_email = os.getenv("N8N_WEBHOOK_ENVIAR_EMAIL")

    payload = {"numero_aviso": numero_aviso}
    resultados = {}
    errors = []

    try:
        if canal == "whatsapp":
            if webhook_wa:
                r = requests.post(webhook_wa, json=payload, timeout=30)
                r.raise_for_status()
                resultados["whatsapp"] = r.status_code
            else:
                errors.append("N8N_WEBHOOK_ENVIAR_WA no configurado")

        elif canal == "sms":
            if webhook_sms:
                r = requests.post(webhook_sms, json=payload, timeout=30)
                r.raise_for_status()
                resultados["sms"] = r.status_code
            else:
                errors.append("N8N_WEBHOOK_ENVIAR_SMS no configurado")

        elif canal == "email":
            if webhook_email:
                r = requests.post(webhook_email, json=payload, timeout=30)
                r.raise_for_status()
                resultados["email"] = r.status_code
            else:
                errors.append("N8N_WEBHOOK_ENVIAR_EMAIL no configurado")

        return jsonify(
            {
                "success": True,
                "mensaje": "Envío iniciado en n8n",
                "resultados": resultados,
                "advertencias": errors,
            }
        )
    except requests.exceptions.Timeout:
        return jsonify({"success": False, "error": "Timeout al contactar n8n"}), 504
    except requests.exceptions.RequestException as e:
        logger.error("Error webhook enviar: %s", str(e))
        return jsonify({"success": False, "error": str(e)}), 502


# ---------------------------------------------------------------------------
# API: reanudar — re-dispara solo los pendientes del aviso
# ---------------------------------------------------------------------------

@difusion_bp.route("/api/difusion/reanudar/<int:numero_aviso>", methods=["POST"])
def reanudar_envio(numero_aviso):
    """
    Marca los registros con error como 'pendiente' y re-dispara los webhooks.
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "error": "Sin conexión a BD"}), 500

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE clientes_envios
                SET estado = 'pendiente', intentos = 0, mensaje_error = NULL
                WHERE numero_aviso = %s AND estado = 'error'
                """,
                (numero_aviso,),
            )
            actualizados = cur.rowcount
        conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
        logger.error("Error reanudar: %s", str(e))
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

    # Volver a disparar webhooks (igual que enviar)
    webhook_wa    = os.getenv("N8N_WEBHOOK_ENVIAR_WA")
    webhook_sms   = os.getenv("N8N_WEBHOOK_ENVIAR_SMS")
    webhook_email = os.getenv("N8N_WEBHOOK_ENVIAR_EMAIL")
    payload = {"numero_aviso": numero_aviso, "solo_pendientes": True}
    resultados = {}

    try:
        if webhook_wa:
            r = requests.post(webhook_wa, json=payload, timeout=30)
            resultados["whatsapp"] = r.status_code
        if webhook_sms:
            r = requests.post(webhook_sms, json=payload, timeout=30)
            resultados["sms"] = r.status_code
        if webhook_email:
            r = requests.post(webhook_email, json=payload, timeout=30)
            resultados["email"] = r.status_code
    except requests.exceptions.RequestException as e:
        logger.warning("Error webhook reanudar: %s", str(e))

    return jsonify(
        {
            "success": True,
            "actualizados": actualizados,
            "mensaje": f"{actualizados} registros reactivados",
            "webhooks": resultados,
        }
    )


# ---------------------------------------------------------------------------
# API: historial — resumen por aviso + canal
# ---------------------------------------------------------------------------

@difusion_bp.route("/api/difusion/historial")
def historial_envios():
    """
    Devuelve el historial resumido usando la vista v_resumen_envios_por_aviso
    y v_resumen_envios_por_canal para el panel derecho.
    """
    limit = request.args.get("limit", 20, type=int)

    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "error": "Sin conexión a BD"}), 500

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Resumen por aviso (SQL directo, sin depender de vistas)
            cur.execute(
                """
                SELECT
                    ce.numero_aviso,
                    ce.canal_enviado,
                    ce.nivel_filtro,
                    COUNT(*) FILTER (WHERE ce.estado = 'enviado')  AS total_enviado,
                    COUNT(*) FILTER (WHERE ce.estado = 'pendiente') AS total_pendiente,
                    COUNT(*) FILTER (WHERE ce.estado = 'error')    AS errores,
                    COUNT(*) FILTER (WHERE ce.estado = 'leido')    AS total_leido,
                    COUNT(*)                                        AS total,
                    MAX(ce.fecha_envio)                             AS ultima_fecha,
                    ROUND(
                        100.0 * COUNT(*) FILTER (WHERE ce.estado IN ('enviado','leido'))
                        / NULLIF(COUNT(*), 0), 1
                    ) AS tasa_exito_pct
                FROM clientes_envios ce
                GROUP BY ce.numero_aviso, ce.canal_enviado, ce.nivel_filtro
                ORDER BY ce.numero_aviso DESC, ce.canal_enviado
                LIMIT %s
                """,
                (limit,),
            )
            por_aviso = cur.fetchall()

            # Resumen por canal (SQL directo)
            cur.execute(
                """
                SELECT
                    ce.canal_enviado,
                    COUNT(*) FILTER (WHERE ce.estado = 'enviado')  AS total_enviado,
                    COUNT(*) FILTER (WHERE ce.estado = 'error')    AS total_error,
                    ROUND(
                        100.0 * COUNT(*) FILTER (WHERE ce.estado IN ('enviado','leido'))
                        / NULLIF(COUNT(*), 0), 1
                    ) AS tasa_exito_pct
                FROM clientes_envios ce
                GROUP BY ce.canal_enviado
                ORDER BY ce.canal_enviado
                """
            )
            por_canal = cur.fetchall()

        resp = jsonify(
            {
                "success": True,
                "por_aviso": [dict(r) for r in por_aviso],
                "por_canal": [dict(r) for r in por_canal],
            }
        )
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
    except psycopg2.Error as e:
        logger.error("Error historial: %s", str(e))
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()
