#!/usr/bin/env python3
"""
Procesador automático de avisos meteorológicos
Orquesta el flujo completo desde JSON a mapas

Uso:
    python procesar_aviso.py <numero_aviso> [--from-db]

Ejemplo:
    python procesar_aviso.py 447
    python procesar_aviso.py 447 --from-db
"""

import os
import sys
import json
import shutil
import subprocess
import logging
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Importar utilidades de LAYOUT
from LAYOUT.utils import (
    descargar_shp, 
    descomprimir_zip,
    seleccionar_dia_critico,
    extraer_departamentos_afectados,
    extraer_provincias_afectadas,
    extraer_distritos_afectados,
    limpiar_temp
)

# Importar funciones de BD
from CONFIG.db import obtener_aviso_por_numero, guardar_aviso_json

def obtener_json_aviso(numero_aviso, desde_db=False):
    """
    Obtiene datos del aviso desde JSON o BD
    
    Args:
        numero_aviso: Número de aviso
        desde_db: Si True, obtiene de BD. Si False, intenta archivo primero.
    
    Returns:
        Datos del aviso en formato dict
    """
    json_dir = os.getenv('JSON_DIR', 'JSON')
    ruta_json = f"{json_dir}/aviso_{numero_aviso}.json"
    
    # Si se solicita desde BD o no existe JSON local
    if desde_db or not os.path.exists(ruta_json):
        logger.info(f"Obteniendo aviso {numero_aviso} desde base de datos...")
        try:
            aviso_dict = obtener_aviso_por_numero(numero_aviso)
            
            if aviso_dict:
                # Guardar JSON para referencia
                os.makedirs(json_dir, exist_ok=True)
                with open(ruta_json, 'w', encoding='utf-8') as f:
                    json.dump(aviso_dict, f, ensure_ascii=False, indent=2)
                logger.info(f"✓ Aviso obtenido de BD y guardado en {ruta_json}")
                return aviso_dict
            else:
                logger.error(f"Aviso {numero_aviso} no encontrado en BD")
                sys.exit(1)
                
        except Exception as e:
            logger.error(f"❌ Error al consultar BD: {e}")
            if not os.path.exists(ruta_json):
                sys.exit(1)
            logger.warning(f"Usando JSON local: {ruta_json}")
    
    # Leer JSON existente
    logger.info(f"Leyendo aviso desde archivo: {ruta_json}")
    with open(ruta_json, 'r', encoding='utf-8') as f:
        datos = json.load(f)
    
    return datos


def determinar_dias_aviso(duracion_horas):
    """
    Determina cuántos días dura el evento
    
    Args:
        duracion_horas: Duración en horas
    
    Returns:
        Número de días (1, 2 o 3)
    """
    # Si dura menos de 24h, es 1 día
    if duracion_horas <= 24:
        return 1
    # Si dura menos de 48h, son 2 días
    elif duracion_horas <= 48:
        return 2
    # Si dura más, son 3 días
    else:
        return 3


def procesar_aviso(numero_aviso, desde_db=False):
    """
    Procesa un aviso meteorológico completo
    
    Args:
        numero_aviso: Número de aviso
        desde_db: Si True, obtiene datos desde BD
    
    Returns:
        Ruta a la carpeta con mapas generados
    """
    logger.info(f"🔄 Procesando aviso {numero_aviso}...")
    
    # 1. Obtener datos del JSON o BD
    datos_aviso = obtener_json_aviso(numero_aviso, desde_db)
    duracion_horas = datos_aviso.get('duracion_horas', 72)
    nivel = datos_aviso.get('nivel', 'NARANJA')
    
    # 2. Determinar días a procesar
    dias_evento = determinar_dias_aviso(duracion_horas)
    logger.info(f"✓ Aviso {numero_aviso}: {nivel}, duración {duracion_horas}h ({dias_evento} días)")
    
    # 3. Crear carpetas temporales y de salida (usar vars de .env)
    temp_base = os.getenv('TEMP_DIR', 'TEMP')
    output_base = os.getenv('OUTPUT_DIR', 'OUTPUT')
    
    temp_dir = f"{temp_base}/aviso_{numero_aviso}"
    output_dir = f"{output_base}/aviso_{numero_aviso}"
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    
    # 4. Descargar SHP para cada día del evento
    shp_paths = {}
    
    for dia in range(1, dias_evento + 1):
        url_key = f"link_shp_dia{dia}"
        if url_key not in datos_aviso:
            logger.warning(f"⚠ URL de SHP para día {dia} no encontrada en datos")
            continue
            
        url = datos_aviso[url_key]
        zip_path = f"{temp_dir}/shp_dia{dia}.zip"
        extract_dir = f"{temp_dir}/dia{dia}"
        
        descargar_shp(url, zip_path)
        descomprimir_zip(zip_path, extract_dir)
        
        shp_path = os.path.join(extract_dir, 'view_aviso.shp')
        if os.path.exists(shp_path):
            shp_paths[f"dia{dia}"] = shp_path
    
    if not shp_paths:
        logger.error("❌ No se encontraron SHP válidos para ningún día")
        return None
    
    # 5. Seleccionar día crítico
    logger.info("\n🔍 Seleccionando día crítico...")
    dia_critico, shp_critico = seleccionar_dia_critico(shp_paths)
    
    # 6. Extraer departamentos afectados
    logger.info("🔍 Extrayendo departamentos afectados...")
    deptos_afectados = extraer_departamentos_afectados(shp_critico)
    
    if not deptos_afectados:
        logger.warning("⚠ No se encontraron departamentos afectados de nivel ALTO")
        return output_dir
    
    # 7. Extraer y guardar provincias y distritos
    logger.info("🔍 Extrayendo provincias y distritos...")
    provincias = extraer_provincias_afectadas(shp_critico)
    distritos = extraer_distritos_afectados(shp_critico)
    
    if provincias is not None:
        provincias.to_csv(f"{output_dir}/provincias_afectadas.csv", index=False)
        logger.info(f"✓ Guardadas {len(provincias)} provincias")
    if distritos is not None:
        distritos.to_csv(f"{output_dir}/distritos_afectados.csv", index=False)
        logger.info(f"✓ Guardados {len(distritos)} distritos")
    
    # 8. Generar mapas para cada departamento
    logger.info(f"🗺️ Generando mapas para {len(deptos_afectados)} departamentos...")
    
    for depto in deptos_afectados:
        logger.info(f"▶ Procesando mapa para {depto}...")
        
        args_mapas = [
            depto,
            str(datos_aviso.get('numero_aviso', '')),
            str(datos_aviso.get('duracion_horas', '')),
            datos_aviso.get('titulo', ''),
            datos_aviso.get('nivel', ''),
            datos_aviso.get('color', ''),
            datos_aviso.get('fecha_emision', ''),
            datos_aviso.get('fecha_inicio', ''),
            datos_aviso.get('fecha_fin', ''),
            datos_aviso.get('descripcion', '')
        ]
        
        # Variables de entorno para MAPAS.py
        env = os.environ.copy()
        env['SHP_RIESGO_PATH'] = shp_critico
        
        cmd = [sys.executable, 'LAYOUT/MAPAS.py'] + args_mapas
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"❌ Error al generar mapa para {depto}:\n{result.stderr}")
            continue
            
        mapa_origen = f"mapa_tematico_{depto}.png"
        mapa_destino = f"{output_dir}/{depto}.webp"
        
        try:
            from PIL import Image
            img = Image.open(mapa_origen)
            img.save(mapa_destino, format="WEBP", quality=90)
            os.remove(mapa_origen)
            logger.info(f"✓ Guardado: {mapa_destino}")
        except ImportError:
            shutil.move(mapa_origen, f"{output_dir}/{depto}.png")
            logger.info(f"✓ Guardado: {output_dir}/{depto}.png")
    
    logger.info(f"\n✅ Procesamiento del aviso {numero_aviso} completado")
    logger.info(f"📁 Mapas guardados en: {output_dir}")
    
    return output_dir


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("❌ Error: Falta número de aviso")
        logger.info(f"Uso: python {os.path.basename(__file__)} <numero_aviso> [--from-db]")
        logger.info("Ejemplos:")
        logger.info(f"  python {os.path.basename(__file__)} 447")
        logger.info(f"  python {os.path.basename(__file__)} 447 --from-db")
        sys.exit(1)
    
    numero_aviso = sys.argv[1]
    desde_db = '--from-db' in sys.argv
    
    try:
        numero_aviso = int(numero_aviso)
        procesar_aviso(numero_aviso, desde_db)
    except ValueError:
        logger.error(f"❌ Error: '{numero_aviso}' no es un número válido")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error inesperado: {e}", exc_info=True)
        sys.exit(1)