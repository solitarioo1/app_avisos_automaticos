"""
Utilidades para procesamiento de avisos meteorológicos
Consolida funcionalidades de los scripts de LAYOUT
"""
import os
import zipfile
import requests
import geopandas as gpd
from pathlib import Path


def descargar_shp(url, destino):
    """
    Descarga un archivo ZIP desde URL y lo guarda en destino
    
    Args:
        url: URL del shapefile ZIP
        destino: Ruta donde guardar el archivo (ej: TEMP/aviso_471/shp_dia1.zip)
    
    Returns:
        Path al archivo descargado
    """
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    with open(destino, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    print(f"✓ Descargado: {destino}")
    return destino


def descomprimir_zip(zip_path, extract_to):
    """
    Descomprime un archivo ZIP
    
    Args:
        zip_path: Ruta al archivo ZIP
        extract_to: Carpeta destino para extraer
    
    Returns:
        Path a la carpeta extraída
    """
    if not os.path.exists(extract_to):
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        print(f"✓ Descomprimido: {extract_to}")
    else:
        print(f"⚠ Ya existe: {extract_to}")
    return extract_to


def calcular_area_riesgo_alto(shp_path):
    """
    Calcula el área total de riesgo alto (Nivel 3 NARANJA + Nivel 4 ROJO)
    
    Args:
        shp_path: Ruta al shapefile view_aviso.shp
    
    Returns:
        Área en km²
    """
    if not os.path.exists(shp_path):
        print(f"⚠ SHP no encontrado: {shp_path}")
        return 0.0
    
    gdf = gpd.read_file(shp_path)
    # Filtrar Nivel 3 (NARANJA) y Nivel 4 (ROJO)
    gdf_alto = gdf[gdf['nivel'].isin(['Nivel 3', 'Nivel 4'])]
    
    if gdf_alto.empty:
        return 0.0
    
    # Reproyectar a UTM zona 18S (EPSG:32718) para Perú
    gdf_alto = gdf_alto.to_crs(epsg=32718)
    area_total = gdf_alto['geometry'].area.sum() / 1_000_000  # m² a km²
    
    return area_total


def seleccionar_dia_critico(dict_shps):
    """
    Selecciona el día con mayor área de riesgo alto
    
    Args:
        dict_shps: {dia: shp_path} ej: {'dia1': 'TEMP/aviso_471/dia1/view_aviso.shp', ...}
    
    Returns:
        Tupla (dia_critico, shp_path_critico)
    """
    areas = {}
    for dia, shp_path in dict_shps.items():
        areas[dia] = calcular_area_riesgo_alto(shp_path)
        print(f"  {dia}: {areas[dia]:.2f} km² de riesgo ALTO")
    
    if not areas:
        raise ValueError("No se calcularon áreas para ningún día")
    
    dia_critico = max(areas, key=areas.get)
    print(f"✓ Día crítico: {dia_critico} ({areas[dia_critico]:.2f} km²)")
    
    return dia_critico, dict_shps[dia_critico]


def extraer_departamentos_afectados(shp_riesgo_path):
    """
    Extrae lista de departamentos afectados por riesgo ALTO (Nivel 3 o 4)
    
    Args:
        shp_riesgo_path: Ruta al shapefile de riesgo del día crítico
    
    Returns:
        Lista de nombres de departamentos (ej: ['CUSCO', 'PUNO', ...])
    """
    shp_riesgo = gpd.read_file(shp_riesgo_path)
    shp_deptos = gpd.read_file('DELIMITACIONES/DEPARTAMENTOS/DEPARTAMENTOS.shp')
    
    # Filtrar solo Nivel 3 (NARANJA) y Nivel 4 (ROJO)
    shp_alto = shp_riesgo[shp_riesgo['nivel'].isin(['Nivel 3', 'Nivel 4'])]
    
    if shp_alto.empty:
        print("⚠ No hay zonas de riesgo ALTO en este aviso")
        return []
    
    # Spatial join para detectar intersección
    shp_alto = shp_alto.to_crs(shp_deptos.crs)
    riesgo_con_depto = gpd.sjoin(shp_alto, shp_deptos, how='left', predicate='intersects')
    
    deptos_afectados = sorted(riesgo_con_depto['DPTONOM02'].dropna().unique())
    print(f"✓ Departamentos afectados: {len(deptos_afectados)}")
    for depto in deptos_afectados:
        print(f"  - {depto}")
    
    return deptos_afectados


def limpiar_temp(aviso_id):
    """
    Limpia la carpeta temporal de un aviso específico
    
    Args:
        aviso_id: Número de aviso (ej: 471)
    """
    import shutil
    temp_path = f"TEMP/aviso_{aviso_id}"
    if os.path.exists(temp_path):
        shutil.rmtree(temp_path)
        print(f"✓ Limpiado: {temp_path}")


def extraer_provincias_afectadas(shp_riesgo_path):
    """
    Extrae provincias afectadas por riesgo ALTO del día crítico
    
    Args:
        shp_riesgo_path: Ruta al shapefile de riesgo del día crítico
    
    Returns:
        DataFrame con columnas: DEPARTAMEN, PROVINCIA
    """
    shp_riesgo = gpd.read_file(shp_riesgo_path)
    shp_provincias = gpd.read_file('DELIMITACIONES/PROVINCIAS/PROVINCIAS.shp')
    
    # Filtrar solo Nivel 3 y 4
    shp_alto = shp_riesgo[shp_riesgo['nivel'].isin(['Nivel 3', 'Nivel 4'])]
    
    if shp_alto.empty:
        return None
    
    # Spatial join con provincias
    shp_alto = shp_alto.to_crs(shp_provincias.crs)
    riesgo_con_prov = gpd.sjoin(shp_alto, shp_provincias, how='left', predicate='intersects')
    
    provincias_afectadas = riesgo_con_prov[['DEPARTAMEN', 'PROVINCIA']].dropna().drop_duplicates()
    print(f"✓ Provincias afectadas: {len(provincias_afectadas)}")
    
    return provincias_afectadas


def extraer_distritos_afectados(shp_riesgo_path):
    """
    Extrae distritos afectados por riesgo ALTO del día crítico
    
    Args:
        shp_riesgo_path: Ruta al shapefile de riesgo del día crítico
    
    Returns:
        DataFrame con columnas: DEPARTAMEN, PROVINCIA, DISTRITO
    """
    shp_riesgo = gpd.read_file(shp_riesgo_path)
    shp_distritos = gpd.read_file('DELIMITACIONES/DISTRITOS/DISTRITOS.shp')
    
    # Filtrar solo Nivel 3 y 4
    shp_alto = shp_riesgo[shp_riesgo['nivel'].isin(['Nivel 3', 'Nivel 4'])]
    
    if shp_alto.empty:
        return None
    
    # Spatial join con distritos
    shp_alto = shp_alto.to_crs(shp_distritos.crs)
    riesgo_con_dist = gpd.sjoin(shp_alto, shp_distritos, how='left', predicate='intersects')
    
    distritos_afectados = riesgo_con_dist[['DEPARTAMEN', 'PROVINCIA', 'DISTRITO']].dropna().drop_duplicates()
    print(f"✓ Distritos afectados: {len(distritos_afectados)}")
    
    return distritos_afectados
