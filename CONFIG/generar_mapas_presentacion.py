"""
CONFIG/generar_mapas_presentacion.py — Genera imágenes PNG de MAPA DE CALOR
(densidad de casos, no promedio por distrito) para Piura y Puno, para presentación,
más un resumen de texto (eventos, % indemnizado, provincia con más pagos).

Cada caso de siniestros_historico se representa como UN PUNTO: coordenada real
donde existe (listar_avisos), o centroide del distrito + jitter aleatorio donde
no hay GPS (la mayoría del historial 2012-2025) — así el mapa refleja densidad
de casos individuales en vez de un solo color promedio por distrito. Los
distritos se dibujan solo como referencia tenue de fondo.
"""
import os
import sys

import contextily as ctx
import geopandas as gpd
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import psycopg2.extras
from shapely.vectorized import contains as shapely_contains

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
from CONFIG.db import get_connection

OUT_DIR = os.path.join(BASE_DIR, 'CONFIG', 'salidas_presentacion')
os.makedirs(OUT_DIR, exist_ok=True)

RNG = np.random.default_rng(42)
JITTER_DEG = 0.025  # ~2.5 km de dispersión alrededor del centroide del distrito
SIGMA_DEG = 0.05     # ~5.5 km, ancho de banda ABSOLUTO del KDE (no proporcional al área del depto)

# Mismo degradado por defecto de Leaflet.heat (la librería que usa el mapa web)
# — así la imagen estática se ve igual que el mapa de calor de mapa-calor-siniestros/.
LEAFLET_HEAT_CMAP = mcolors.LinearSegmentedColormap.from_list('leaflet_heat', [
    (0.0, '#0000ff'), (0.4, '#0000ff'), (0.6, '#00ffff'),
    (0.7, '#00ff00'), (0.8, '#ffff00'), (1.0, '#ff0000'),
])


def _kde_manual(xs, ys, pesos, grid_x, grid_y, sigma):
    """Suma de gaussianas 2D con sigma fijo — a diferencia de scipy.gaussian_kde,
    el ancho de banda no depende de la dispersión total de los puntos, así que
    focos de concentración real (ej. un distrito con 600 casos) se ven como
    manchas puntuales y no se diluyen en un solo degradado departamental."""
    gx, gy = grid_x.ravel(), grid_y.ravel()
    dens = np.zeros(gx.shape[0])
    chunk = 400
    for i in range(0, len(xs), chunk):
        dx = gx[:, None] - xs[i:i + chunk][None, :]
        dy = gy[:, None] - ys[i:i + chunk][None, :]
        w = pesos[i:i + chunk][None, :]
        dens += np.sum(w * np.exp(-(dx ** 2 + dy ** 2) / (2 * sigma ** 2)), axis=1)
    return dens.reshape(grid_x.shape)


def _casos_departamento(departamento):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT distrito, resultado, latitud, longitud
        FROM siniestros_historico
        WHERE departamento = %s AND resultado IN ('INDEMNIZADO', 'NO_INDEMNIZADO')
    """, (departamento,))
    filas = cur.fetchall()
    cur.close(); conn.close()
    return filas


def _resumen_departamento(departamento):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE resultado = 'INDEMNIZADO') AS indemnizados,
            COUNT(*) FILTER (WHERE resultado = 'NO_INDEMNIZADO') AS no_indemnizados,
            COUNT(*) FILTER (WHERE resultado = 'SIN_DATO') AS sin_dato,
            COALESCE(SUM(monto_indemnizable) FILTER (WHERE resultado = 'INDEMNIZADO'), 0) AS monto_total
        FROM siniestros_historico WHERE departamento = %s
    """, (departamento,))
    resumen = cur.fetchone()

    cur.execute("""
        SELECT provincia,
               COUNT(*) FILTER (WHERE resultado = 'INDEMNIZADO') AS indemnizados,
               COALESCE(SUM(monto_indemnizable) FILTER (WHERE resultado = 'INDEMNIZADO'), 0) AS monto_total
        FROM siniestros_historico
        WHERE departamento = %s AND provincia IS NOT NULL
        GROUP BY provincia
        ORDER BY monto_total DESC
        LIMIT 5
    """, (departamento,))
    provincias = cur.fetchall()
    cur.close(); conn.close()

    base = resumen['indemnizados'] + resumen['no_indemnizados']
    resumen['pct_indemnizado'] = round(100 * resumen['indemnizados'] / base, 1) if base else None
    resumen['monto_total'] = float(resumen['monto_total'])
    for p in provincias:
        p['monto_total'] = float(p['monto_total'])
    return resumen, provincias


def generar_mapa_calor(departamento, archivo_salida):
    shp_path = os.path.join(BASE_DIR, 'DELIMITACIONES', 'DISTRITOS', 'DISTRITOS.shp')
    gdf_dist = gpd.read_file(shp_path)
    gdf_dist = gdf_dist[gdf_dist['DEPARTAMEN'].str.upper() == departamento.upper()].copy()
    centroides = {row['DISTRITO'].upper(): row.geometry.centroid for _, row in gdf_dist.iterrows()}
    limite_depto = gdf_dist.geometry.union_all()

    filas = _casos_departamento(departamento)
    xs, ys, pesos = [], [], []
    con_gps = 0
    for f in filas:
        if f['latitud'] is not None and f['longitud'] is not None:
            lon, lat = f['longitud'], f['latitud']
            con_gps += 1
        else:
            c = centroides.get((f['distrito'] or '').upper())
            if c is None:
                continue
            lon = c.x + RNG.normal(0, JITTER_DEG)
            lat = c.y + RNG.normal(0, JITTER_DEG)
        xs.append(lon)
        ys.append(lat)
        pesos.append(1.0 if f['resultado'] == 'INDEMNIZADO' else 0.35)

    xs, ys, pesos = np.array(xs), np.array(ys), np.array(pesos)
    print(f"  {departamento}: {len(xs)} puntos ({con_gps} con GPS real, {len(xs)-con_gps} centroide+jitter)")

    minx, miny, maxx, maxy = gdf_dist.total_bounds
    margen_x, margen_y = (maxx - minx) * 0.08, (maxy - miny) * 0.08
    grid_x, grid_y = np.mgrid[minx - margen_x:maxx + margen_x:340j, miny - margen_y:maxy + margen_y:340j]

    # KDE manual con sigma FIJO en grados (~4 km) — gaussian_kde escala el ancho
    # de banda según la covarianza total de los datos, lo que en un departamento
    # entero termina fusionando todos los focos en una sola banda difusa.
    densidad = _kde_manual(xs, ys, pesos, grid_x, grid_y, sigma=SIGMA_DEG)

    # Enmascarar fuera del departamento (para no pintar densidad en zonas vecinas)
    mascara = shapely_contains(limite_depto, grid_x, grid_y)
    densidad_mask = np.where(mascara, densidad, np.nan)

    # RGBA manual (no pcolormesh) para controlar la transparencia por celda —
    # así se ve igual que Leaflet.heat en la web: donde no hay densidad se ve
    # el mapa real de calles/relieve de OpenStreetMap por debajo, sin mancha
    # de color tapando todo el departamento.
    pico = np.nanmax(densidad_mask)
    intensidad = np.clip(densidad_mask / (pico * 0.55), 0, 1)  # satura antes del máximo -> focos más vivos
    intensidad = np.nan_to_num(intensidad, nan=0.0)
    alpha = intensidad ** 0.6  # sube visibilidad de densidades medias/bajas

    rgba = LEAFLET_HEAT_CMAP(intensidad)
    rgba[..., 3] = alpha
    rgba[np.isnan(densidad_mask), 3] = 0.0  # fuera del depto, 100% transparente

    fig, ax = plt.subplots(1, 1, figsize=(9, 11))
    ax.set_xlim(minx - margen_x, maxx + margen_x)
    ax.set_ylim(miny - margen_y, maxy + margen_y)

    # OSM Mapnik directo bloquea descargas automatizadas grandes (403, tile usage
    # policy) y CartoDB ahora exige API key (tiles con marca de agua) — Esri
    # WorldStreetMap es gratis, sin key, y visualmente similar (calles, nombres).
    ctx.add_basemap(ax, crs='EPSG:4326', source=ctx.providers.Esri.WorldStreetMap, attribution=False)

    # imshow espera filas=Y, columnas=X — el grid viene de mgrid como (X,Y), y transponer
    ax.imshow(
        np.transpose(rgba, (1, 0, 2)),
        extent=(minx - margen_x, maxx + margen_x, miny - margen_y, maxy + margen_y),
        origin='lower', interpolation='bilinear', zorder=3
    )

    # Distritos como referencia tenue de fondo (segundo plano, sin etiquetas)
    gdf_dist.boundary.plot(ax=ax, color='#333', linewidth=0.5, alpha=0.5, zorder=4)

    ax.set_title(f'Mapa de Calor — Siniestros Indemnizados en {departamento.title()}', fontsize=14, fontweight='bold', pad=14)
    ax.set_axis_off()
    fig.patch.set_facecolor('white')
    fig.tight_layout()
    ruta = os.path.join(OUT_DIR, archivo_salida)
    fig.savefig(ruta, dpi=200, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"✅ Mapa de calor guardado: {ruta}")


BURBUJA_COLOR = '#7fe8e8'  # cian claro


def _stats_por_distrito(departamento):
    """Total de casos por distrito (todos los resultados) — tamaño de burbuja."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT distrito, COUNT(*) AS total,
               COUNT(*) FILTER (WHERE resultado = 'INDEMNIZADO') AS indemnizados
        FROM siniestros_historico
        WHERE departamento = %s AND distrito IS NOT NULL
        GROUP BY distrito
    """, (departamento,))
    filas = {r['distrito']: r for r in cur.fetchall()}
    cur.close(); conn.close()
    return filas


def generar_mapa_burbujas(departamento, archivo_salida):
    """Mapa de burbujas estilo Power BI: un círculo por distrito, área proporcional
    a la cantidad de casos, un solo color — sobre el mismo mapa base real."""
    shp_path = os.path.join(BASE_DIR, 'DELIMITACIONES', 'DISTRITOS', 'DISTRITOS.shp')
    gdf_dist = gpd.read_file(shp_path)
    gdf_dist = gdf_dist[gdf_dist['DEPARTAMEN'].str.upper() == departamento.upper()].copy()

    stats = _stats_por_distrito(departamento)
    gdf_dist['total'] = gdf_dist['DISTRITO'].str.upper().map(lambda d: stats.get(d, {}).get('total', 0))
    gdf_dist['indemnizados'] = gdf_dist['DISTRITO'].str.upper().map(lambda d: stats.get(d, {}).get('indemnizados', 0))
    gdf_dist['cx'] = gdf_dist.geometry.centroid.x
    gdf_dist['cy'] = gdf_dist.geometry.centroid.y

    con_datos = gdf_dist[gdf_dist['indemnizados'] > 0].copy()

    minx, miny, maxx, maxy = gdf_dist.total_bounds
    margen_x, margen_y = (maxx - minx) * 0.08, (maxy - miny) * 0.08

    fig, ax = plt.subplots(1, 1, figsize=(9, 11))
    ax.set_xlim(minx - margen_x, maxx + margen_x)
    ax.set_ylim(miny - margen_y, maxy + margen_y)
    # Fondo plano color melón (relleno de distrito) en vez de mapa de calles —
    # menos distracción visual detrás de las burbujas, mismo estilo que mapa_piura.png.
    gdf_dist.plot(ax=ax, color='#fbdcc4', edgecolor='#333', linewidth=0.6, zorder=2)

    # Área proporcional (no radio) — estándar cartográfico, evita exagerar diferencias.
    max_indem = con_datos['indemnizados'].max() if len(con_datos) else 1
    tam_min, tam_max = 60, 3200
    con_datos['tamano'] = tam_min + (con_datos['indemnizados'] / max_indem) ** 0.5 * (tam_max - tam_min)

    ax.scatter(
        con_datos['cx'], con_datos['cy'], s=con_datos['tamano'],
        color=BURBUJA_COLOR, alpha=0.65, edgecolor='#0d7377', linewidth=1.1, zorder=4
    )

    # Etiquetar los 5 distritos con más casos indemnizados
    top5 = con_datos.nlargest(5, 'indemnizados')
    for _, row in top5.iterrows():
        ax.annotate(
            f"{row['DISTRITO'].title()}\n({row['indemnizados']})", xy=(row['cx'], row['cy']),
            fontsize=8, fontweight='bold', color='#222', ha='center', va='center', zorder=5,
            bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='none', alpha=0.75)
        )

    ax.set_title(f'Siniestros Indemnizados por Distrito — {departamento.title()}\n(tamaño = cantidad de casos indemnizados)',
                 fontsize=14, fontweight='bold', pad=14)
    ax.set_axis_off()
    fig.patch.set_facecolor('white')
    fig.tight_layout()
    ruta = os.path.join(OUT_DIR, archivo_salida)
    fig.savefig(ruta, dpi=200, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"✅ Mapa de burbujas guardado: {ruta}")


def main():
    for depto, archivo in [('PIURA', 'mapa_calor_piura.png'), ('PUNO', 'mapa_calor_puno.png')]:
        print(f"\n{'='*70}\n{depto}\n{'='*70}")
        generar_mapa_calor(depto, archivo)
        resumen, provincias = _resumen_departamento(depto)
        print(f"Total eventos: {resumen['total']}")
        print(f"Indemnizados (SÍ pagado): {resumen['indemnizados']}")
        print(f"No indemnizados (NO pagado): {resumen['no_indemnizados']}")
        print(f"Sin dato: {resumen['sin_dato']}")
        print(f"% Indemnizado: {resumen['pct_indemnizado']}%")
        print(f"Monto total pagado: S/ {resumen['monto_total']:,.0f}")
        print("Top provincias por monto pagado:")
        for p in provincias:
            print(f"  - {p['provincia']}: {p['indemnizados']} pagados, S/ {p['monto_total']:,.0f}")


if __name__ == '__main__':
    main()
