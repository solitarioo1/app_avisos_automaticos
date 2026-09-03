"""
CONFIG/consolidar_siniestros.py — Consolida los 8 excels de SINIESTROS/ (historial
2013-2026, distintos formatos entre sí) en una sola tabla `siniestros_historico`.

Fuentes y qué aporta cada una:
- I a V_AGROBANCO...xlsx (2013-2018): tienen el resultado real del ajuste
  (columna RESULTADO LP o RESULTADO AJUSTE: INDEMNIZABLE / NO INDEMNIZABLE /
  DESISTIMIENTO / RECHAZADO / ...) y MONTO INDEMNIZABLE. Solo departamento/
  provincia/distrito, sin coordenadas.
- SINIESTROS - Agrobanco 1 y 2 de 2.xlsx (2018-2025): la hoja 'SINIESTROS' NO
  tiene resultado, pero la hoja 'AJUSTADOR' sí — columna 'RESULTADO' (Excel AA,
  invisible con header por defecto porque el encabezado real está en la fila 1)
  + 'Monto a indemnizar'. Se usa AJUSTADOR como fuente. Solo depto/prov/distrito,
  sin coordenadas. Quedan "SIN_DATO" únicamente las pocas filas donde ni
  siquiera AJUSTADOR tiene RESULTADO cargado (196 de 1978 en el archivo "2 de 2").
- listar_avisos_...xlsx (dic 2023 - jul 2026): tiene LATITUD/LONGITUD reales
  y 'Fechas de pago de indemnización' — si es '-' no se pagó (NO_INDEMNIZADO),
  si trae fecha, sí (INDEMNIZADO). Es el único con GPS punto a punto.

Se puede volver a correr cuando se actualicen los excels (upsert por fuente+fila).
"""
import os
import re
import sys
import unicodedata

import pandas as pd
import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from CONFIG.db import get_connection

CARPETA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'SINIESTROS')


_TEXTO_INVALIDO = {'', 'NAN', 'NONE', 'NULL', 'N/A', '-'}


def _norm_texto(valor, mayusculas=True):
    """Limpia texto libre (provincia/distrito/cultivo/evento). Descarta también
    los casos donde el excel origen trae literalmente el texto "NaN" pegado
    (fórmula rota tipo VLOOKUP sin resolver) — no es un valor real, hay que
    tratarlo como nulo igual que un NaN de verdad, si no ensucia los rankings."""
    if pd.isna(valor):
        return None
    txt = str(valor).strip()
    txt = txt.upper() if mayusculas else txt
    if txt.upper() in _TEXTO_INVALIDO:
        return None
    return txt or None


def _norm_depto(valor):
    txt = _norm_texto(valor)
    if txt is None:
        return None
    txt = unicodedata.normalize('NFKD', txt).encode('ascii', 'ignore').decode('ascii')
    txt = re.sub(r'\s+', ' ', txt)
    return txt or None


# Variantes de escritura del mismo evento (con/sin tilde, huaico/huayco) que
# aparecían como valores distintos en el selector — se homogenizan a una sola.
_EVENTO_ALIAS = {
    'INUNDACION': 'INUNDACIÓN',
    'HUAYCO O DESLIZAMIENTO': 'HUAICO O DESLIZAMIENTO',
    'HUAICO O DESLIZAMIENTO DE TERRENO': 'HUAICO O DESLIZAMIENTO',
}


def _norm_evento(valor):
    txt = _norm_texto(valor)
    if txt is None or txt.isdigit():  # "0" literal, dato basura
        return None
    return _EVENTO_ALIAS.get(txt, txt)


def _norm_resultado(valor):
    """Colapsa todas las variantes/typos de RESULTADO LP / RESULTADO AJUSTE
    a un set fijo: INDEMNIZADO, NO_INDEMNIZADO, DESISTIMIENTO, RECHAZADO,
    EXCLUIDO, PENDIENTE, OTRO. None si no hay dato."""
    if pd.isna(valor):
        return None
    txt = str(valor).strip().upper()
    txt = re.sub(r'\s+', ' ', txt)
    if 'NO INDEMNIZ' in txt:
        return 'NO_INDEMNIZADO'
    if 'INDEMNIZ' in txt:
        return 'INDEMNIZADO'
    if 'DESISTIM' in txt or 'DESESTIM' in txt:
        return 'DESISTIMIENTO'
    if 'RECHAZ' in txt:
        return 'RECHAZADO'
    if 'EXCLUI' in txt:
        return 'EXCLUIDO'
    if 'PENDIENTE' in txt:
        return 'PENDIENTE'
    if 'FUERA DE VIGENCIA' in txt:
        return 'FUERA_VIGENCIA'
    return 'OTRO'


def _to_float(valor):
    try:
        v = float(valor)
        return v if v == v else None  # descarta NaN
    except (TypeError, ValueError):
        return None


def _fecha_valida(dt):
    """Descarta fechas de digitación (ej. año 0203 en vez de 2013) fuera del
    rango real de historial del negocio. Filtro defensivo, mismo patrón usado
    para los sentinels de precipitación en evaluación de riesgo."""
    if pd.isna(dt):
        return pd.NaT
    if dt.year < 2000 or dt.year > 2027:
        return pd.NaT
    return dt


def _cargar_agrobanco_con_resultado(fname, hoja, col_resultado_principal, col_resultado_fallback=None):
    """Para los 5 archivos I-V_AGROBANCO: tienen RESULTADO LP/AJUSTE + MONTO INDEMNIZABLE."""
    ruta = os.path.join(CARPETA, fname)
    header = 1 if fname.startswith('I_AGROBANCO') else 0
    df = pd.read_excel(ruta, sheet_name=hoja, header=header)
    df = df.dropna(subset=['ASEGURADO']) if 'ASEGURADO' in df.columns else df.dropna(how='all')

    filas = []
    for _, r in df.iterrows():
        resultado_raw = r.get(col_resultado_principal)
        if pd.isna(resultado_raw) and col_resultado_fallback:
            resultado_raw = r.get(col_resultado_fallback)
        filas.append({
            'fuente': fname,
            'fecha_evento': _fecha_valida(pd.to_datetime(r.get('FECHA DEL EVENTO'), errors='coerce')),
            'departamento': _norm_depto(r.get('DEPARTAMENTO')),
            'provincia': _norm_texto(r.get('PROVINCIA')),
            'distrito': _norm_texto(r.get('DISTRITO')),
            'cultivo': _norm_texto(r.get('CULTIVO'), mayusculas=False),
            'evento': _norm_evento(r.get('EVENTO')),
            'monto_indemnizable': _to_float(r.get('MONTO INDEMNIZABLE')),
            'resultado_raw': str(resultado_raw).strip() if pd.notna(resultado_raw) else None,
            'resultado': _norm_resultado(resultado_raw),
            'area_asegurada': _to_float(r.get('AREA ASEGURADA')),
            'latitud': None,
            'longitud': None,
        })
    return filas


def _cargar_agrobanco_ajustador(fname):
    """Para 'SINIESTROS - Agrobanco 1/2 de 2.xlsx': la hoja 'SINIESTROS' no tiene
    resultado, pero la hoja 'AJUSTADOR' sí (columna 'RESULTADO', AA en Excel —
    invisible con header por defecto porque su fila de encabezados real es la 1,
    no la 0). Usamos AJUSTADOR como fuente principal para estos dos archivos."""
    ruta = os.path.join(CARPETA, fname)
    df = pd.read_excel(ruta, sheet_name='AJUSTADOR', header=1)
    df = df.dropna(subset=['ID LP'])

    filas = []
    for _, r in df.iterrows():
        resultado_raw = r.get('RESULTADO')
        filas.append({
            'fuente': fname,
            'fecha_evento': _fecha_valida(pd.to_datetime(r.get('FECHA OCURRENCIA'), errors='coerce')),
            'departamento': _norm_depto(r.get('Departamento')),
            'provincia': _norm_texto(r.get('Provincia')),
            'distrito': _norm_texto(r.get('Distrito')),
            'cultivo': _norm_texto(r.get('Cultivo'), mayusculas=False),
            'evento': _norm_evento(r.get('Evento')),
            'monto_indemnizable': _to_float(r.get('Monto a indemnizar')),
            'resultado_raw': str(resultado_raw).strip() if pd.notna(resultado_raw) else None,
            'resultado': _norm_resultado(resultado_raw) if pd.notna(resultado_raw) else 'SIN_DATO',
            'area_asegurada': _to_float(r.get('Área asegurada (Has)')),
            'latitud': None,
            'longitud': None,
        })
    return filas


def _cargar_listar_avisos(fname):
    """listar_avisos_...xlsx: tiene GPS real + fecha de pago -> indemnizado o no."""
    ruta = os.path.join(CARPETA, fname)
    df = pd.read_excel(ruta, sheet_name='Worksheet')

    filas = []
    for _, r in df.iterrows():
        pago = r.get('Fechas de pago de indemnización')
        pago_txt = str(pago).strip() if pd.notna(pago) else ''
        tiene_pago = pago_txt not in ('', '-', 'nan', 'NaT')
        filas.append({
            'fuente': fname,
            'fecha_evento': _fecha_valida(pd.to_datetime(r.get('FECHA OCURRENCIA'), errors='coerce')),
            'departamento': _norm_depto(r.get('Departamento')),
            'provincia': str(r.get('Provincia')).strip().upper() if pd.notna(r.get('Provincia')) else None,
            'distrito': str(r.get('Distrito')).strip().upper() if pd.notna(r.get('Distrito')) else None,
            'cultivo': str(r.get('Cultivo')).strip() if pd.notna(r.get('Cultivo')) else None,
            'evento': _norm_evento(r.get('Evento Real')) or _norm_evento(r.get('Evento Reportado')),
            'monto_indemnizable': None,
            'resultado_raw': pago_txt or None,
            'resultado': 'INDEMNIZADO' if tiene_pago else 'NO_INDEMNIZADO',
            'area_asegurada': _to_float(r.get('Area asegurada (Has)')),
            'latitud': _to_float(r.get('Latitud')),
            'longitud': _to_float(r.get('Longitud')),
        })
    return filas


def consolidar():
    print("Leyendo excels de SINIESTROS/ ...")
    todas = []
    todas += _cargar_agrobanco_con_resultado('I_AGROBANCO - SINIESTROS - Caso 1 al 482.xlsx', 'SINIESTROS LP', 'RESULTADO LP', 'RESULTADO AJUSTE ')
    todas += _cargar_agrobanco_con_resultado('II_AGROBANCO - SINIESTROS - Caso 483 al 1167.xlsx', 'SINIESTROS LP', 'RESULTADO LP', 'RESULTADO AJUSTE ')
    todas += _cargar_agrobanco_con_resultado('III_AGROBANCO - SINIESTROS - Caso 1168 al 2701.xlsx', 'SINIESTROS LP', 'RESULTADO LP', 'RESULTADO AJUSTE ')
    todas += _cargar_agrobanco_con_resultado('IV AGROBANCO - SINIESTROS -Caso 2701 al 3884 final.xlsx', 'SINIESTROS LP', 'RESULTADO AJUSTE ', 'RESULTADO AJUSTE .1')
    todas += _cargar_agrobanco_con_resultado('V_AGROBANCO - SINIESTROS - Caso del 3885 al 5435.xlsx', 'SINIESTROS', 'RESULTADO AJUSTE ', 'RESULTADO AJUSTE .1')
    todas += _cargar_agrobanco_ajustador('SINIESTROS - Agrobanco, 1 de 2.xlsx')
    todas += _cargar_agrobanco_ajustador('SINIESTROS - Agrobanco, 2 de 2.xlsx')
    todas += _cargar_listar_avisos('listar_avisos_2026-09-01_08-36-02.xlsx')

    df = pd.DataFrame(todas)
    df = df.dropna(subset=['departamento'])  # sin depto no sirve para el mapa
    print(f"Total filas consolidadas: {len(df)}")
    print(df['resultado'].value_counts(dropna=False))
    print(df.groupby('fuente').size())

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS siniestros_historico (
            id SERIAL PRIMARY KEY,
            fuente VARCHAR(120) NOT NULL,
            fecha_evento DATE,
            departamento VARCHAR(60),
            provincia VARCHAR(80),
            distrito VARCHAR(80),
            cultivo VARCHAR(120),
            evento VARCHAR(80),
            monto_indemnizable NUMERIC,
            resultado_raw VARCHAR(120),
            resultado VARCHAR(30),
            area_asegurada DOUBLE PRECISION,
            latitud DOUBLE PRECISION,
            longitud DOUBLE PRECISION,
            cargado_en TIMESTAMP DEFAULT now()
        )
    """)
    cur.execute("ALTER TABLE siniestros_historico ADD COLUMN IF NOT EXISTS area_asegurada DOUBLE PRECISION")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_siniestros_depto ON siniestros_historico(departamento)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_siniestros_resultado ON siniestros_historico(resultado)")
    conn.commit()

    # Reemplazo completo (re-ejecutable sin duplicar)
    cur.execute("TRUNCATE TABLE siniestros_historico RESTART IDENTITY")

    def _limpio(v):
        # El roundtrip por DataFrame convierte None -> NaN, y esto NO es solo
        # cosa de columnas numéricas: pandas hace lo mismo en columnas de texto
        # con huecos (mezcla None/str) — el NaN de un campo de texto (ej.
        # 'distrito') termina insertado como el STRING literal "NaN" en Postgres
        # (Postgres castea float NaN -> texto así). Hay que limpiar TODOS los
        # campos que vienen de df.to_dict('records'), no solo los numéricos.
        return None if pd.isna(v) else v

    def _limpio_num(v):
        v = _limpio(v)
        return float(v) if v is not None else None

    filas_insert = [
        (
            _limpio(r['fuente']),
            r['fecha_evento'].date() if pd.notna(r['fecha_evento']) else None,
            _limpio(r['departamento']), _limpio(r['provincia']), _limpio(r['distrito']),
            _limpio(r['cultivo']), _limpio(r['evento']),
            _limpio_num(r['monto_indemnizable']), _limpio(r['resultado_raw']), _limpio(r['resultado']),
            _limpio_num(r['area_asegurada']),
            _limpio_num(r['latitud']), _limpio_num(r['longitud']),
        )
        for r in df.to_dict('records')
    ]
    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO siniestros_historico
           (fuente, fecha_evento, departamento, provincia, distrito, cultivo, evento,
            monto_indemnizable, resultado_raw, resultado, area_asegurada, latitud, longitud)
           VALUES %s""",
        filas_insert
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ {len(filas_insert)} filas cargadas en siniestros_historico")


if __name__ == '__main__':
    consolidar()
