"""
Módulo de conexión a base de datos PostgreSQL
Maneja consultas de avisos SENAMHI
"""

import psycopg2
import psycopg2.extras
import json
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def get_connection():
    """
    Obtiene conexión a PostgreSQL desde variables de entorno
    
    Variables de entorno requeridas:
    - DB_HOST: Host del servidor (default: localhost)
    - DB_PORT: Puerto (default: 5432)
    - DB_NAME: Nombre de base de datos
    - DB_USER: Usuario
    - DB_PASSWORD: Contraseña
    
    Returns:
        Connection: Objeto de conexión psycopg2
        
    Raises:
        psycopg2.Error: Si falla la conexión
    """
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )
        logger.info("Conexión a BD establecida")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Error conectando a BD: {str(e)}")
        raise


def obtener_aviso_por_numero(numero_aviso: int) -> Optional[Dict[str, Any]]:
    """
    Obtiene un aviso de la base de datos por número
    
    Args:
        numero_aviso: Número del aviso a consultar
        
    Returns:
        Dict con datos del aviso o None si no existe
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute(
            "SELECT * FROM avisos_completos WHERE numero_aviso = %s",
            (numero_aviso,)
        )
        aviso = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if aviso:
            logger.info(f"Aviso {numero_aviso} obtenido de BD")
            # Convertir objetos date/datetime a strings para JSON serialization
            aviso_dict = dict(aviso)
            for key, value in aviso_dict.items():
                if hasattr(value, 'isoformat'):  # date, datetime, time objects
                    aviso_dict[key] = value.isoformat()
            return aviso_dict
        else:
            logger.warning(f"Aviso {numero_aviso} no encontrado en BD")
            return None
            
    except psycopg2.Error as e:
        logger.error(f"Error consultando BD: {str(e)}")
        return None


def guardar_aviso_json(numero_aviso: int, output_path: str = ".") -> bool:
    """
    Descarga un aviso de BD y lo guarda en archivo JSON
    
    Args:
        numero_aviso: Número del aviso
        output_path: Ruta donde guardar el JSON (default: directorio actual)
        
    Returns:
        bool: True si se guardó exitosamente
    """
    try:
        aviso = obtener_aviso_por_numero(numero_aviso)
        
        if not aviso:
            return False
        
        filepath = os.path.join(output_path, f"aviso_{numero_aviso}.json")
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(aviso, f, default=str, indent=2, ensure_ascii=False)
        
        logger.info(f"Aviso guardado en: {filepath}")
        return True
        
    except Exception as e:
        logger.error(f"Error guardando JSON: {str(e)}")
        return False


def limpiar_imagenes_aviso(numero_aviso: int) -> bool:
    """Elimina datos viejos de un aviso antes de regenerar"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM imagenes_avisos WHERE numero_aviso = %s", (numero_aviso,))
        cursor.execute("DELETE FROM archivos_csv_avisos WHERE numero_aviso = %s", (numero_aviso,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Datos limpios para aviso {numero_aviso}")
        return True
    except Exception as e:
        logger.error(f"Error limpiando datos: {str(e)}")
        return False


def guardar_imagen_aviso(numero_aviso: int, departamento: str, ruta_webp: str) -> bool:
    """Guarda ruta de imagen WEBP en BD"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """INSERT INTO imagenes_avisos (numero_aviso, departamento, ruta_webp, estado)
               VALUES (%s, %s, %s, 'completado')
               ON CONFLICT (numero_aviso, departamento) DO UPDATE
               SET ruta_webp = EXCLUDED.ruta_webp, fecha_creacion = CURRENT_TIMESTAMP""",
            (numero_aviso, departamento, ruta_webp)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Imagen guardada: Aviso {numero_aviso} - {departamento}")
        return True
    except Exception as e:
        logger.error(f"Error guardando imagen: {str(e)}")
        return False


def guardar_csv_aviso(numero_aviso: int, tipo: str, ruta_csv: str) -> bool:
    """Guarda ruta de CSV en BD"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """INSERT INTO archivos_csv_avisos (numero_aviso, tipo, ruta_csv)
               VALUES (%s, %s, %s)
               ON CONFLICT DO NOTHING""",
            (numero_aviso, tipo, ruta_csv)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"CSV guardado: Aviso {numero_aviso} - {tipo}")
        return True
    except Exception as e:
        logger.error(f"Error guardando CSV: {str(e)}")
        return False


if __name__ == "__main__":
    # Para pruebas locales
    logging.basicConfig(level=logging.INFO)
    aviso = obtener_aviso_por_numero(447)
    if aviso:
        print(json.dumps(aviso, default=str, indent=2, ensure_ascii=False))