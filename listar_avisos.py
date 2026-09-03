#!/usr/bin/env python3
"""
Script para listar todos los avisos disponibles en la base de datos
"""

import logging
import os
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def listar_avisos_bd():
    """Lista todos los avisos disponibles en la BD"""
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Query para obtener resumen de avisos
        query = """
        SELECT 
            numero_aviso,
            COUNT(*) as dias,
            MIN(fecha_emision) as fecha_emision,
            MAX(fecha_fin) as fecha_fin
        FROM avisos_completos
        GROUP BY numero_aviso
        ORDER BY numero_aviso DESC
        """
        
        cursor.execute(query)
        avisos = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        if avisos:
            logger.info(f"✅ Total de avisos encontrados: {len(avisos)}")
            print("\n" + "="*70)
            print(f"{'ID AVISO':<12} {'DÍAS':<8} {'FECHA EMISION':<20} {'FECHA FIN':<20}")
            print("="*70)
            for aviso in avisos:
                print(f"{aviso['numero_aviso']:<12} {aviso['dias']:<8} {str(aviso['fecha_emision']):<20} {str(aviso['fecha_fin']):<20}")
            print("="*70)
        else:
            logger.warning("❌ No hay avisos en la base de datos")
            
    except psycopg2.Error as e:
        logger.error(f"❌ Error conectando a BD: {str(e)}")


if __name__ == "__main__":
    listar_avisos_bd()
