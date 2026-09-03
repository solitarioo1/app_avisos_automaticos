"""
recorte_zona_agricola.py — Recorta las capas de peligro (livianas) al área
agrícola nacional, y genera el buffer del río principal (reemplazo de
CAPA_FAJA_MARGINAL). Deja las capas pesadas (INUNDACION, MOVIMIENTO_MASA)
fuera de este script: esas se trabajan en ArcGIS Pro.

Salida: CAPAS/CAPAS_PROCESADAS/*.geojson
"""
import logging
import os
import time

import geopandas as gpd
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPAS = os.path.join(BASE, "CAPAS")
OUT = os.path.join(CAPAS, "CAPAS_PROCESADAS")
os.makedirs(OUT, exist_ok=True)

CRS_METRICO = "EPSG:32718"  # UTM 18S, buena aproximación para todo Perú a esta escala de buffer
CRS_GEO = "EPSG:4326"

CAPAS_PELIGRO = {
    "friaje": os.path.join(CAPAS, "CAPA_FRIAJE", "susc_friaje.shp"),
    "helada": os.path.join(CAPAS, "CAPA_HELADA", "susc_heladas.shp"),
    "sequia": os.path.join(CAPAS, "CAPA_SEQUIA_METEOROLOGICA", "sequia_meteorologica.shp"),
    "viento": os.path.join(CAPAS, "CAPA_VIENTO", "viento_fuerte.shp"),
    "incendios": os.path.join(CAPAS, "CAPA_INCENDIOS_FORESTALES", "riesgo_dist_erif_2025.shp"),
}


def paso(msg):
    logger.info(f"▶ {msg}")


def main():
    t0 = time.time()

    # 1) Unir los 19 shp de zona agrícola en una sola capa nacional
    paso("Uniendo shapefiles de CAPA_SUPERFICIE_AGRICOLA...")
    carpeta_agro = os.path.join(CAPAS, "CAPA_SUPERFICIE_AGRICOLA")
    archivos = [f for f in os.listdir(carpeta_agro) if f.lower().endswith(".shp")]
    logger.info(f"  {len(archivos)} departamentos encontrados")
    partes = []
    for f in archivos:
        gdf = gpd.read_file(os.path.join(carpeta_agro, f))
        gdf = gdf[gdf.geometry.notnull() & gdf.geometry.is_valid]
        partes.append(gdf[["geometry"]])
    zona_agricola = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs=CRS_GEO)
    logger.info(f"  ✅ {len(zona_agricola)} polígonos unidos ({time.time()-t0:.0f}s)")

    # 2) Buffer 300m + disolver en un solo polígono de recorte
    paso("Aplicando buffer de 300m y disolviendo...")
    zona_utm = zona_agricola.to_crs(CRS_METRICO)
    zona_utm["geometry"] = zona_utm.geometry.buffer(300)
    recorte = zona_utm.dissolve().to_crs(CRS_GEO)
    recorte_path = os.path.join(OUT, "zona_agricola_buffer.geojson")
    recorte.to_file(recorte_path, driver="GeoJSON")
    logger.info(f"  ✅ buffer listo ({time.time()-t0:.0f}s) -> {recorte_path}")

    # 3) Recortar cada capa de peligro liviana
    for nombre, ruta in CAPAS_PELIGRO.items():
        paso(f"Recortando {nombre}...")
        if not os.path.exists(ruta):
            logger.warning(f"  ⚠️ no encontrado: {ruta}")
            continue
        gdf = gpd.read_file(ruta)
        gdf = gdf[gdf.geometry.notnull() & gdf.geometry.is_valid]
        if gdf.crs is None:
            gdf = gdf.set_crs(CRS_GEO)
        elif gdf.crs.to_string() != CRS_GEO:
            gdf = gdf.to_crs(CRS_GEO)
        recortado = gpd.clip(gdf, recorte)
        out_path = os.path.join(OUT, f"{nombre}_clip.geojson")
        recortado.to_file(out_path, driver="GeoJSON")
        logger.info(f"  ✅ {nombre}: {len(gdf)} -> {len(recortado)} features ({time.time()-t0:.0f}s) -> {out_path}")

    # 4) Buffer de río principal, en 4 bandas de distancia (Faja Marginal)
    # Niveles pedidos (3 sep 2026): Muy Alto <100m, Alto <500m, Medio <1km,
    # Bajo >1km. El usuario pidió "Bajo" SIN límite superior — no puede ser
    # literalmente infinito (el polígono terminaría cubriendo casi todo el
    # Perú y rompería el filtro de exposición de Mapa Clientes), así que se
    # acota a 5km de borde exterior como límite práctico (antes probé 2km,
    # muy corto: un punto a 3km quedaba "sin clasificar" en vez de Bajo).
    paso("Generando buffer de río principal (4 bandas de distancia)...")
    BANDAS_FAJA = [(100, "Muy Alto"), (500, "Alto"), (1000, "Medio"), (5000, "Bajo")]

    rios_path = os.path.join(CAPAS, "CAPA_RIOS_DEPARTAMENTO", "Rios_quebradas_ANA_geogpsperu_SuyoPomalia.shp")
    rios = gpd.read_file(rios_path)
    rios = rios[rios.geometry.notnull() & rios.geometry.is_valid]
    rios_principales = rios[rios["TIPO_CA"] == "Río"].copy()
    logger.info(f"  {len(rios_principales)} tramos de río (de {len(rios)} totales, excluyendo quebradas)")

    # BUG encontrado (3 sep 2026): el shapefile de ríos cubre TODO el Perú
    # (-81° a -68° de longitud), es decir los 3 husos UTM del país (17S/18S/
    # 19S). Bufferear todo con un solo huso fijo (18S, meridiano central -75°)
    # distorsiona fuerte lejos de ese meridiano — en Piura (~650km de -75°) el
    # buffer salía visiblemente corrido del cauce real en el mapa. Fix: cada
    # tramo se bufferea en SU PROPIO huso según la longitud de su centroide.
    def _huso_utm(lon):
        if lon >= -78:
            return 32718  # UTM 18S
        if lon >= -84:
            return 32717  # UTM 17S
        return 32719      # UTM 19S (extremo sur-oriente, por si acaso)

    centroides_geo = rios_principales.geometry.to_crs(CRS_GEO).centroid
    rios_principales["_huso"] = centroides_geo.x.apply(_huso_utm)

    bandas_por_huso = []
    for huso, grupo in rios_principales.groupby("_huso"):
        grupo_utm = grupo.to_crs(huso)
        anillos = []
        buffer_anterior = None
        for distancia, nivel in BANDAS_FAJA:
            buffer_actual = grupo_utm.geometry.buffer(distancia).unary_union
            anillo = buffer_actual if buffer_anterior is None else buffer_actual.difference(buffer_anterior)
            # Simplificar (tolerancia en metros, en el huso métrico) — sin esto
            # el archivo salía de 522MB (947 tramos de río con vértices muy
            # densos heredados del shapefile ANA) en vez de los pocos MB que
            # debería pesar un "preview" liviano (ver otras capas en
            # CAPAS_PROCESADAS/, todas entre 0.7 y 40MB). 15m bajó a 112MB,
            # todavía pesado — 45m (banda "Bajo" nacional a 2km es la que más
            # pesa) para acercarlo al resto.
            anillo = anillo.simplify(45, preserve_topology=True)
            anillos.append({"nivel": nivel, "distancia_m": distancia, "geometry": anillo})
            buffer_anterior = buffer_actual
        gdf_anillos = gpd.GeoDataFrame(anillos, crs=huso).to_crs(CRS_GEO)
        bandas_por_huso.append(gdf_anillos)
        logger.info(f"    huso {huso}: {len(grupo)} tramos bufferizados")

    # Mismo nivel puede venir de varios husos (ej. un río que cruza el límite
    # de zona) — se disuelve por nivel para que quede una sola banda continua.
    todas = pd.concat(bandas_por_huso, ignore_index=True)
    todas = gpd.GeoDataFrame(todas, crs=CRS_GEO)
    rio_buffer = todas.dissolve(by="nivel", as_index=False)
    orden_nivel = {n: i for i, (_, n) in enumerate(BANDAS_FAJA)}
    rio_buffer["_orden"] = rio_buffer["nivel"].map(orden_nivel)
    rio_buffer = rio_buffer.sort_values("_orden").drop(columns="_orden")

    rio_path = os.path.join(OUT, "rio_principal_buffer.geojson")
    rio_buffer.to_file(rio_path, driver="GeoJSON")
    logger.info(f"  ✅ buffer de río listo, 4 bandas ({time.time()-t0:.0f}s) -> {rio_path}")

    logger.info(f"\n🎉 Terminado en {time.time()-t0:.0f}s. Salida en {OUT}")


if __name__ == "__main__":
    main()
