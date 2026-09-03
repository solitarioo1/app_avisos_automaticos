"""
Pre-genera GeoJSON simplificado por departamento para las capas pesadas
(zona_agricola, sector_estadistico) usadas en /seguimiento-cultivo.

Simplificar al vuelo en cada request es demasiado lento (15-30s por
departamento en zona_agricola, por la cantidad de vértices de origen).
Este script se corre UNA VEZ (o cuando cambien los shapefiles fuente) y
deja los resultados listos en CONFIG/geojson_cache/, que la ruta Flask
sirve directo del disco.

Uso:
    python CONFIG/precache_capas.py
"""
import sys
import time
from pathlib import Path

import geopandas as gpd

BASE_DIR = Path(__file__).parent.parent
CAPAS_DIR = BASE_DIR / 'CAPAS'
CACHE_DIR = BASE_DIR / 'CONFIG' / 'geojson_cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(BASE_DIR))
from routes.seguimiento_cultivo import _normalizar  # noqa: E402

# nombre_capa -> (carpeta, tolerancia_simplify_en_grados)
CAPAS_A_CACHEAR = {
    'zona_agricola': ('CAPA_SUPERFICIE_AGRICOLA', 0.001),      # ~110m, capa de fondo
    'sector_estadistico': ('CAPA_SECTORES_ESTADISTICOS', 0.0003),  # ~30m, ya es rápida pero cacheamos igual
}

COLUMNAS_UTILES = (
    'NOMBDEP', 'NOMBPROV', 'NOMBDIST', 'NOM_SE', 'CATEGORIA', 'USO',
    'AREA_HA', 'AREA_SE', 'CAPITAL', 'geometry'
)


def procesar_archivo(archivo: Path, tolerancia: float):
    gdf = gpd.read_file(archivo)

    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    columnas = [c for c in gdf.columns if c in COLUMNAS_UTILES]
    gdf = gdf[columnas]

    for col in gdf.columns:
        if col != 'geometry' and gdf[col].dtype.kind == 'M':
            gdf[col] = gdf[col].astype(str)

    gdf['geometry'] = gdf['geometry'].simplify(tolerancia, preserve_topology=True)
    return gdf


def main():
    inicio_total = time.time()

    for nombre_capa, (carpeta, tolerancia) in CAPAS_A_CACHEAR.items():
        archivos = sorted((CAPAS_DIR / carpeta).glob('*.shp'))
        print(f"\n=== {nombre_capa} ({len(archivos)} archivos) ===")

        for archivo in archivos:
            # nombre tipo "12_JUNIN_SuperficieAgricola.shp" -> extraer depto
            partes = archivo.stem.split('_')
            # el departamento suele ser el/los tokens entre el código numérico
            # inicial y el nombre de la capa al final; probamos con gdf['NOMBDEP']
            # para no depender de parsear el nombre de archivo.
            t0 = time.time()
            try:
                gdf = procesar_archivo(archivo, tolerancia)
            except Exception as e:
                print(f"  ERROR {archivo.name}: {e}")
                continue

            if gdf.empty or 'NOMBDEP' not in gdf.columns:
                print(f"  {archivo.name}: sin filas o sin columna NOMBDEP, se omite")
                continue

            depto = _normalizar(gdf['NOMBDEP'].iloc[0]).replace(' ', '_')
            destino = CACHE_DIR / f"{nombre_capa}_{depto}.geojson"
            destino.write_text(gdf.to_json(), encoding='utf-8')

            t1 = time.time()
            print(f"  {depto}: {len(gdf)} filas, {destino.stat().st_size // 1024} KB, {round(t1 - t0, 1)}s")

    print(f"\nListo. Total: {round(time.time() - inicio_total, 1)}s")


if __name__ == '__main__':
    main()
