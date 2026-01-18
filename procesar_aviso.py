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

# Configurar logging con flush inmediato
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    force=True
)
logger = logging.getLogger(__name__)

# Asegurar que stdout se flush inmediatamente
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

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
from CONFIG.db import obtener_aviso_por_numero, guardar_aviso_json, limpiar_imagenes_aviso, guardar_imagen_aviso, guardar_csv_aviso

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
    print(f"\n📢 AVISO #{numero_aviso}\n", flush=True)
    
    # 0. Limpiar datos viejos de BD antes de regenerar
    limpiar_imagenes_aviso(numero_aviso)
    logger.info(f"Datos viejos limpiados para aviso {numero_aviso}")
    
    # 1. Obtener datos del JSON o BD
    print(f"⏳ Iniciando la descarga de información...", flush=True)
    datos_aviso = obtener_json_aviso(numero_aviso, desde_db)
    duracion_horas = datos_aviso.get('duracion_horas', 72)
    nivel = datos_aviso.get('nivel', 'NARANJA')
    
    # Validar que solo se generen mapas para ROJO y NARANJA
    if nivel not in ['ROJO', 'NARANJA']:
        print(f"\n⚠️  Este aviso es de nivel {nivel.upper()}", flush=True)
        print(f"📌 Los mapas solo se generan para avisos ROJO y NARANJA", flush=True)
        print(f"\n✅ Procesamiento finalizado\n", flush=True)
        logger.warning(f"⚠ Aviso {numero_aviso} es de nivel {nivel} - Mapas solo se generan para ROJO y NARANJA")
        # Crear output_dir aunque sea, pero sin mapas
        output_base = os.getenv('OUTPUT_DIR', 'OUTPUT')
        output_dir = f"{output_base}/aviso_{numero_aviso}"
        os.makedirs(output_dir, exist_ok=True)
        return output_dir
    
    # 2. Determinar días a procesar
    dias_evento = determinar_dias_aviso(duracion_horas)
    print(f"\n📅 Duración del evento: {duracion_horas} horas ({dias_evento} día{'s' if dias_evento > 1 else ''})", flush=True)
    
    # 3. Crear carpetas temporales y de salida (usar vars de .env)
    temp_base = os.getenv('TEMP_DIR', 'TEMP')
    output_base = os.getenv('OUTPUT_DIR', 'OUTPUT')
    
    temp_dir = f"{temp_base}/aviso_{numero_aviso}"
    output_dir = f"{output_base}/aviso_{numero_aviso}"
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    
    # 4. Descargar SHP para cada día del evento
    print(f"\n🌐 Descargando mapas de riesgo...", flush=True)
    shp_paths = {}
    
    for dia in range(1, dias_evento + 1):
        url_key = f"link_shp_dia{dia}"
        if url_key not in datos_aviso:
            logger.warning(f"⚠ URL de SHP para día {dia} no encontrada en datos")
            continue
            
        url = datos_aviso[url_key]
        zip_path = f"{temp_dir}/shp_dia{dia}.zip"
        extract_dir = f"{temp_dir}/dia{dia}"
        
        print(f"  ⬇️  Día {dia}... ", end="", flush=True)
        descargar_shp(url, zip_path)
        descomprimir_zip(zip_path, extract_dir)
        print(f"✅", flush=True)
        
        shp_path = os.path.join(extract_dir, 'view_aviso.shp')
        if os.path.exists(shp_path):
            shp_paths[f"dia{dia}"] = shp_path
    
    if not shp_paths:
        logger.error("❌ No se encontraron SHP válidos para ningún día")
        return None
    
    # 5. Seleccionar día crítico
    print(f"\n🔍 Analizando zonas de riesgo...", flush=True)
    dia_critico, shp_critico = seleccionar_dia_critico(shp_paths)
    print(f"  ✅ Día seleccionado: {dia_critico}", flush=True)
    
    # 6. Extraer departamentos afectados
    print(f"\n🗺️  Identificando zonas afectadas...", flush=True)
    deptos_afectados = extraer_departamentos_afectados(shp_critico)
    
    if not deptos_afectados:
        print(f"⚠️  No se encontraron áreas de riesgo alto en este aviso", flush=True)
        print(f"\n✅ Procesamiento finalizado\n", flush=True)
        logger.warning("⚠ No se encontraron departamentos afectados de nivel ALTO")
        return output_dir
    
    # 7. Extraer y guardar provincias y distritos
    provincias = extraer_provincias_afectadas(shp_critico)
    distritos = extraer_distritos_afectados(shp_critico)
    
    num_provincias = len(provincias) if provincias is not None else 0
    num_distritos = len(distritos) if distritos is not None else 0
    
    print(f"\n📍 Áreas afectadas:", flush=True)
    print(f"  🏛️  Departamentos: {len(deptos_afectados)}", flush=True)
    print(f"  🏢 Provincias: {num_provincias}", flush=True)
    print(f"  🏘️  Distritos: {num_distritos}", flush=True)
    
    if provincias is not None:
        provincias.to_csv(f"{output_dir}/provincias_afectadas.csv", index=False)
        guardar_csv_aviso(numero_aviso, 'provincias', f"/static/output/aviso_{numero_aviso}/provincias_afectadas.csv")
    if distritos is not None:
        distritos.to_csv(f"{output_dir}/distritos_afectados.csv", index=False)
        guardar_csv_aviso(numero_aviso, 'distritos', f"/static/output/aviso_{numero_aviso}/distritos_afectados.csv")
    
    # 8. Generar mapas para cada departamento
    print(f"\n⏱️  TIEMPO ESTIMADO: ~{len(deptos_afectados)} minutos", flush=True)
    print(f"💡 Recomendación: Sé paciente, esto puede tomar un tiempo...", flush=True)
    print(f"\n🎨 COMENZANDO GENERACIÓN DE MAPAS\n", flush=True)
    
    for idx, depto in enumerate(deptos_afectados, 1):
        print(f"  [{idx}/{len(deptos_afectados)}] Generando mapa para {depto}...", end=" ", flush=True)
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
            print(f"❌ ERROR", flush=True)
            continue
            
        mapa_origen = f"mapa_tematico_{depto}.png"
        mapa_destino = f"{output_dir}/{depto}.webp"
        
        try:
            from PIL import Image
            img = Image.open(mapa_origen)
            img.save(mapa_destino, format="WEBP", quality=90)
            os.remove(mapa_origen)
            logger.info(f"✓ Guardado: {mapa_destino}")
            print(f"✅ CREADO", flush=True)
            
            # Guardar ruta en BD
            ruta_relativa = f"/static/output/aviso_{numero_aviso}/{depto}.webp"
            guardar_imagen_aviso(numero_aviso, depto, ruta_relativa)
            
        except ImportError:
            shutil.move(mapa_origen, f"{output_dir}/{depto}.png")
            logger.info(f"✓ Guardado: {output_dir}/{depto}.png")
            print(f"✅ CREADO", flush=True)
            
            # Guardar ruta en BD (formato PNG si PIL no está disponible)
            ruta_relativa = f"/static/output/aviso_{numero_aviso}/{depto}.png"
            guardar_imagen_aviso(numero_aviso, depto, ruta_relativa)
    
    print(f"\n✨ CREACIÓN FINALIZADA ✨\n", flush=True)
    print(f"👋 ¡Hasta pronto! Esta pestaña se cerrará en 5 segundos...\n", flush=True)
    logger.info(f"\n✅ Procesamiento del aviso {numero_aviso} completado")
    logger.info(f"📁 Mapas guardados en: {output_dir}")


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