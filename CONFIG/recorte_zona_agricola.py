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

    # 4) Buffer de río principal (reemplazo de CAPA_FAJA_MARGINAL)
    paso("Generando buffer de río principal (100m a cada lado)...")
    rios_path = os.path.join(CAPAS, "CAPA_RIOS_DEPARTAMENTO", "Rios_quebradas_ANA_geogpsperu_SuyoPomalia.shp")
    rios = gpd.read_file(rios_path)
    rios = rios[rios.geometry.notnull() & rios.geometry.is_valid]
    rios_principales = rios[rios["TIPO_CA"] == "Río"].copy()
    logger.info(f"  {len(rios_principales)} tramos de río (de {len(rios)} totales, excluyendo quebradas)")
    rios_utm = rios_principales.to_crs(CRS_METRICO)
    rios_utm["geometry"] = rios_utm.geometry.buffer(100)
    rio_buffer = rios_utm.dissolve().to_crs(CRS_GEO)
    rio_path = os.path.join(OUT, "rio_principal_buffer.geojson")
    rio_buffer.to_file(rio_path, driver="GeoJSON")
    logger.info(f"  ✅ buffer de río listo ({time.time()-t0:.0f}s) -> {rio_path}")

    logger.info(f"\n🎉 Terminado en {time.time()-t0:.0f}s. Salida en {OUT}")


if __name__ == "__main__":
    main()
