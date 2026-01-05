#!/usr/bin/env python3
"""
Script para descargar avisos desde base de datos
Obtiene un aviso de BD y lo guarda en JSON para procesamiento

Uso:
    python descargar_aviso.py <numero_aviso>
    python descargar_aviso.py <numero_aviso> --procesar

Ejemplo:
    python descargar_aviso.py 447
    python descargar_aviso.py 447 --procesar
"""

import sys
import os
import logging
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Importar función de BD
from CONFIG.db import guardar_aviso_json


def descargar_aviso(numero_aviso: int, procesar: bool = False) -> bool:
    """
    Descarga un aviso de BD y lo guarda en JSON
    
    Args:
        numero_aviso: Número del aviso a descargar
        procesar: Si True, ejecuta procesar_aviso.py después
        
    Returns:
        bool: True si se descargó exitosamente
    """
    logger.info(f"📥 Descargando aviso {numero_aviso} desde base de datos...")
    
    # Crear carpeta JSON si no existe
    json_dir = os.getenv('JSON_DIR', 'JSON')
    os.makedirs(json_dir, exist_ok=True)
    
    try:
        # Guardar JSON desde BD en carpeta JSON/
        exito = guardar_aviso_json(numero_aviso, output_path=json_dir)
        
        if not exito:
            logger.error(f"❌ No se pudo descargar aviso {numero_aviso}")
            return False
        
        logger.info(f"✅ Aviso {numero_aviso} descargado exitosamente")
        logger.info(f"📄 Guardado: {json_dir}/aviso_{numero_aviso}.json")
        
        # Si se solicita, ejecutar procesar_aviso.py
        if procesar:
            logger.info(f"\n🔄 Iniciando procesamiento del aviso {numero_aviso}...")
            cmd = [sys.executable, "procesar_aviso.py", str(numero_aviso)]
            result = subprocess.run(cmd, capture_output=False, text=True)
            
            if result.returncode != 0:
                logger.error(f"❌ Error al procesar aviso {numero_aviso}")
                return False
            
            logger.info(f"✅ Aviso {numero_aviso} procesado completamente")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}", exc_info=True)
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("❌ Error: Falta número de aviso")
        logger.info(f"Uso: python {os.path.basename(__file__)} <numero_aviso> [--procesar]")
        logger.info("Ejemplos:")
        logger.info(f"  python {os.path.basename(__file__)} 447")
        logger.info(f"  python {os.path.basename(__file__)} 447 --procesar")
        sys.exit(1)
    
    try:
        numero_aviso = int(sys.argv[1])
        procesar = "--procesar" in sys.argv
        
        exito = descargar_aviso(numero_aviso, procesar)
        sys.exit(0 if exito else 1)
        
    except ValueError:
        logger.error(f"❌ Error: '{sys.argv[1]}' no es un número válido")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error inesperado: {e}", exc_info=True)
        sys.exit(1)
