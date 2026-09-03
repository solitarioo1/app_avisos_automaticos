"""
routes/mapa_calor_siniestros.py — Mapa de calor de siniestros históricos (2013-2026):
dónde se pagó (INDEMNIZADO) y dónde no, por departamento (todo el historial) y por
punto GPS real donde existe (solo listar_avisos, dic 2023 - jul 2026).
Datos poblados por CONFIG/consolidar_siniestros.py en la tabla siniestros_historico.
"""
import logging
import re
import unicodedata

import psycopg2.extras
from flask import Blueprint, jsonify, render_template, request

from CONFIG.db import get_connection

logger = logging.getLogger(__name__)

mapa_calor_siniestros_bp = Blueprint('mapa_calor_siniestros', __name__, url_prefix='/mapa-calor-siniestros')


def _agrupar_por_especie(filas):
    """El cultivo crudo viene como "PAPA//CANCHAN...", "PAPA/COMERCIAL",
    "PAPA//TODAS" — separador y tildes inconsistentes entre variedades del
    mismo cultivo. Se agrupa por lo que hay antes de la primera '/', sin
    tildes, para que todas las variedades sumen junto a su especie."""
    agrupado = {}
    for f in filas:
        base = f['cultivo'].split('/')[0].strip().upper()
        base = unicodedata.normalize('NFKD', base).encode('ascii', 'ignore').decode('ascii')
        base = re.sub(r'\s+', ' ', base)
        if not base:
            continue
        acc = agrupado.setdefault(base, {'cultivo': base, 'indemnizados': 0, 'monto_total': 0})
        acc['indemnizados'] += f['indemnizados']
        acc['monto_total'] += float(f['monto_total'])
    return sorted(agrupado.values(), key=lambda x: x['indemnizados'], reverse=True)[:8]


def _filtro_anios(incluir_depto=False):
    where, params = [], []
    anio_desde = request.args.get('anio_desde', type=int)
    anio_hasta = request.args.get('anio_hasta', type=int)
    evento = request.args.get('evento')
    if anio_desde:
        where.append("EXTRACT(YEAR FROM fecha_evento) >= %s")
        params.append(anio_desde)
    if anio_hasta:
        where.append("EXTRACT(YEAR FROM fecha_evento) <= %s")
        params.append(anio_hasta)
    if evento:
        where.append("evento = %s")
        params.append(evento.upper())
    if incluir_depto:
        departamento = request.args.get('departamento')
        if departamento:
            where.append("departamento = %s")
            params.append(departamento.upper())
    return where, params


@mapa_calor_siniestros_bp.route('/')
def index():
    return render_template('mapa_calor_siniestros.html')


@mapa_calor_siniestros_bp.route('/api/departamentos')
def api_departamentos():
    """Agregado por departamento: total, indemnizados, no indemnizados, sin dato, % y monto."""
    where, params = _filtro_anios()
    where = ["departamento IS NOT NULL"] + where
    where_sql = " AND ".join(where)

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(f"""
            SELECT
                departamento,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE resultado = 'INDEMNIZADO') AS indemnizados,
                COUNT(*) FILTER (WHERE resultado = 'NO_INDEMNIZADO') AS no_indemnizados,
                COUNT(*) FILTER (WHERE resultado = 'SIN_DATO') AS sin_dato,
                COUNT(*) FILTER (WHERE resultado NOT IN ('INDEMNIZADO','NO_INDEMNIZADO','SIN_DATO')) AS otros,
                COALESCE(SUM(monto_indemnizable) FILTER (WHERE resultado = 'INDEMNIZADO'), 0) AS monto_total
            FROM siniestros_historico
            WHERE {where_sql}
            GROUP BY departamento
            ORDER BY total DESC
        """, params)
        filas = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    resultado = []
    for f in filas:
        base = f['indemnizados'] + f['no_indemnizados']
        f['pct_indemnizado'] = round(100 * f['indemnizados'] / base, 1) if base else None
        f['monto_total'] = float(f['monto_total'])
        resultado.append(f)
    return jsonify(resultado)


@mapa_calor_siniestros_bp.route('/api/distritos')
def api_distritos():
    """Agregado por distrito, filtrado a uno o más departamentos (?departamentos=PIURA,PUNO)."""
    where, params = _filtro_anios()
    where = ["departamento IS NOT NULL", "distrito IS NOT NULL"] + where

    deptos_raw = request.args.get('departamentos', '')
    deptos = [d.strip().upper() for d in deptos_raw.split(',') if d.strip()]
    if deptos:
        where.append("departamento = ANY(%s)")
        params.append(deptos)
    where_sql = " AND ".join(where)

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(f"""
            SELECT
                departamento, distrito,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE resultado = 'INDEMNIZADO') AS indemnizados,
                COUNT(*) FILTER (WHERE resultado = 'NO_INDEMNIZADO') AS no_indemnizados,
                COUNT(*) FILTER (WHERE resultado = 'SIN_DATO') AS sin_dato,
                COUNT(*) FILTER (WHERE resultado NOT IN ('INDEMNIZADO','NO_INDEMNIZADO','SIN_DATO')) AS otros,
                COALESCE(SUM(monto_indemnizable) FILTER (WHERE resultado = 'INDEMNIZADO'), 0) AS monto_total
            FROM siniestros_historico
            WHERE {where_sql}
            GROUP BY departamento, distrito
            ORDER BY monto_total DESC
        """, params)
        filas = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    resultado = []
    for f in filas:
        base = f['indemnizados'] + f['no_indemnizados']
        f['pct_indemnizado'] = round(100 * f['indemnizados'] / base, 1) if base else None
        f['monto_total'] = float(f['monto_total'])
        resultado.append(f)
    return jsonify(resultado)


@mapa_calor_siniestros_bp.route('/api/puntos')
def api_puntos():
    """Puntos GPS reales (solo la fuente listar_avisos trae coordenadas) para el heat layer fino."""
    where, params = _filtro_anios()
    where = ["latitud IS NOT NULL", "longitud IS NOT NULL"] + where
    where_sql = " AND ".join(where)

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(f"""
            SELECT latitud, longitud, resultado, departamento, evento,
                   fecha_evento, monto_indemnizable
            FROM siniestros_historico
            WHERE {where_sql}
        """, params)
        filas = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    for f in filas:
        if f.get('fecha_evento'):
            f['fecha_evento'] = f['fecha_evento'].isoformat()
        if f.get('monto_indemnizable') is not None:
            f['monto_indemnizable'] = float(f['monto_indemnizable'])
    return jsonify(filas)


@mapa_calor_siniestros_bp.route('/api/eventos')
def api_eventos():
    """Tipos de evento distintos registrados, para el filtro del selector."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT DISTINCT evento FROM siniestros_historico
            WHERE evento IS NOT NULL AND evento <> '' ORDER BY evento
        """)
        eventos = [r[0] for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()
    return jsonify(eventos)


@mapa_calor_siniestros_bp.route('/api/kpis')
def api_kpis():
    where, params = _filtro_anios(incluir_depto=True)
    where_sql = " AND ".join(where) if where else "1=1"

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(f"""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE resultado = 'INDEMNIZADO') AS indemnizados,
                COUNT(*) FILTER (WHERE resultado = 'NO_INDEMNIZADO') AS no_indemnizados,
                COUNT(*) FILTER (WHERE resultado = 'SIN_DATO') AS sin_dato,
                COALESCE(SUM(monto_indemnizable) FILTER (WHERE resultado = 'INDEMNIZADO'), 0) AS monto_total,
                MIN(fecha_evento) AS fecha_min, MAX(fecha_evento) AS fecha_max
            FROM siniestros_historico WHERE {where_sql}
        """, params)
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    base = row['indemnizados'] + row['no_indemnizados']
    row['pct_indemnizado'] = round(100 * row['indemnizados'] / base, 1) if base else None
    row['monto_total'] = float(row['monto_total'])
    for k in ('fecha_min', 'fecha_max'):
        if row.get(k):
            row[k] = row[k].isoformat()
    return jsonify(row)


@mapa_calor_siniestros_bp.route('/api/resumen')
def api_resumen():
    """Panel de análisis: top distritos, eventos climáticos y cultivos — nacional
    si no se manda ?departamento=, o acotado a ese departamento si se manda.
    Todo por casos indemnizados (lo que le importa a seguros: dónde y en qué se pagó)."""
    where, params = _filtro_anios(incluir_depto=True)
    where_sql = " AND ".join(where) if where else "1=1"

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(f"""
            SELECT distrito,
                   COUNT(*) FILTER (WHERE resultado = 'INDEMNIZADO') AS indemnizados,
                   COALESCE(SUM(monto_indemnizable) FILTER (WHERE resultado = 'INDEMNIZADO'), 0) AS monto_total
            FROM siniestros_historico
            WHERE {where_sql} AND distrito IS NOT NULL
            GROUP BY distrito HAVING COUNT(*) FILTER (WHERE resultado = 'INDEMNIZADO') > 0
            ORDER BY indemnizados DESC LIMIT 8
        """, params)
        distritos = cur.fetchall()

        cur.execute(f"""
            SELECT evento,
                   COUNT(*) FILTER (WHERE resultado = 'INDEMNIZADO') AS indemnizados,
                   COUNT(*) AS total
            FROM siniestros_historico
            WHERE {where_sql} AND evento IS NOT NULL
            GROUP BY evento HAVING COUNT(*) FILTER (WHERE resultado = 'INDEMNIZADO') > 0
            ORDER BY indemnizados DESC LIMIT 8
        """, params)
        eventos = cur.fetchall()

        # Por especie, no por variedad: el excel origen trae "PAPA//CANCHAN...",
        # "PAPA/COMERCIAL", "PAPA//TODAS", etc. — se agrupa por lo que hay antes
        # de la primera '/' (todas las variedades de un mismo cultivo cuentan
        # juntas), sin límite acá porque el top-8 real sale después de sumar.
        cur.execute(f"""
            SELECT cultivo,
                   COUNT(*) FILTER (WHERE resultado = 'INDEMNIZADO') AS indemnizados,
                   COALESCE(SUM(monto_indemnizable) FILTER (WHERE resultado = 'INDEMNIZADO'), 0) AS monto_total
            FROM siniestros_historico
            WHERE {where_sql} AND cultivo IS NOT NULL
            GROUP BY cultivo HAVING COUNT(*) FILTER (WHERE resultado = 'INDEMNIZADO') > 0
        """, params)
        cultivos = _agrupar_por_especie(cur.fetchall())

        top_departamentos = []
        if not request.args.get('departamento'):
            where_sin_depto, params_sin_depto = _filtro_anios(incluir_depto=False)
            where_sql_sd = " AND ".join(where_sin_depto) if where_sin_depto else "1=1"
            cur.execute(f"""
                SELECT departamento,
                       COUNT(*) FILTER (WHERE resultado = 'INDEMNIZADO') AS indemnizados,
                       COALESCE(SUM(monto_indemnizable) FILTER (WHERE resultado = 'INDEMNIZADO'), 0) AS monto_total
                FROM siniestros_historico
                WHERE {where_sql_sd} AND departamento IS NOT NULL
                GROUP BY departamento HAVING COUNT(*) FILTER (WHERE resultado = 'INDEMNIZADO') > 0
                ORDER BY indemnizados DESC LIMIT 8
            """, params_sin_depto)
            top_departamentos = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    for grupo in (distritos, eventos, cultivos, top_departamentos):
        for f in grupo:
            if 'monto_total' in f:
                f['monto_total'] = float(f['monto_total'])

    return jsonify({'distritos': distritos, 'eventos': eventos, 'cultivos': cultivos, 'departamentos': top_departamentos})
