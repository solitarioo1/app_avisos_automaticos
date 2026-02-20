"""
Módulo de conexión a base de datos PostgreSQL
Maneja consultas de avisos SENAMHI
"""

import psycopg2
import psycopg2.extras
import pandas as pd
import json
import os
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

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


def limpiar_datos_aviso(numero_aviso: int) -> bool:
    """
    Limpia registros viejos de un aviso antes de regenerar
    
    Args:
        numero_aviso: Número de aviso a limpiar
    
    Returns:
        bool: True si se limpió exitosamente
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Limpiar clientes_por_aviso (la FK en clientes_envios se mantiene)
        cursor.execute("DELETE FROM clientes_por_aviso WHERE numero_aviso = %s", (numero_aviso,))
        # Limpiar aviso_zonas_afectadas
        cursor.execute("DELETE FROM aviso_zonas_afectadas WHERE numero_aviso = %s", (numero_aviso,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Datos limpios para aviso {numero_aviso}")
        return True
    except Exception as e:
        logger.error(f"Error limpiando datos del aviso {numero_aviso}: {str(e)}")
        return False


def insertar_zonas_afectadas(numero_aviso: int, df_zonas) -> int:
    """
    Inserta provincias y distritos en aviso_zonas_afectadas
    
    Args:
        numero_aviso: Número de aviso
        df_zonas: DataFrame con columnas: 'departamento', 'provincia', 'distrito', 'area_km2'
    
    Returns:
        int: Cantidad de registros insertados
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Eliminar registros previos del aviso para evitar duplicados (especialmente con distrito=NULL)
        cursor.execute("DELETE FROM aviso_zonas_afectadas WHERE numero_aviso = %s", (numero_aviso,))

        insertados = 0
        
        for _, row in df_zonas.iterrows():
            cursor.execute(
                """INSERT INTO aviso_zonas_afectadas 
                   (numero_aviso, departamento, provincia, distrito, area_km2)
                   VALUES (%s, %s, %s, %s, %s)""",
                (numero_aviso, row.get('departamento'), row.get('provincia'), row.get('distrito'),
                 row.get('area_km2', 0))
            )
            insertados += cursor.rowcount
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Insertadas {insertados} zonas para aviso {numero_aviso}")
        return insertados
    except Exception as e:
        logger.error(f"Error insertando zonas: {str(e)}")
        return 0


def insertar_clientes_por_aviso(numero_aviso: int, df_clientes) -> int:
    """
    Inserta clientes en clientes_por_aviso
    
    Args:
        numero_aviso: Número de aviso
        df_clientes: DataFrame con columnas: 'id' (o 'cliente_id'), 'nivel'
    
    Returns:
        int: Cantidad de registros insertados
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        insertados = 0
        
        # Determinar nombre correcto de columna de cliente
        cliente_col = 'cliente_id' if 'cliente_id' in df_clientes.columns else 'id'
        
        for _, row in df_clientes.iterrows():
            cliente_id = int(row.get(cliente_col, 0))
            if cliente_id > 0:
                cursor.execute(
                    """INSERT INTO clientes_por_aviso 
                       (cliente_id, numero_aviso, nivel)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (cliente_id, numero_aviso) DO NOTHING""",
                    (cliente_id, numero_aviso, row.get('nivel', 'N/A'))
                )
                insertados += cursor.rowcount
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Insertados {insertados} clientes para aviso {numero_aviso}")
        return insertados
    except Exception as e:
        logger.error(f"Error insertando clientes: {str(e)}")
        return 0


# ============================================================================
# HELPERS PARA LEER DESDE VISTAS (reemplaza CSVs)
# ============================================================================

def obtener_clientes_por_aviso(numero_aviso: int) -> Optional[pd.DataFrame]:
    """
    Obtiene clientes clasificados por aviso desde vista v_clientes_por_aviso_completo
    Reemplaza: lectura de clientes_por_nivel_dia{X}.csv
    
    Args:
        numero_aviso: Número de aviso
    
    Returns:
        pd.DataFrame con columnas: cliente_id, nombre, nivel, hectareas, etc.
    """
    try:
        conn = get_connection()
        df = pd.read_sql_query(
            "SELECT * FROM v_clientes_por_aviso_completo WHERE numero_aviso = %s",
            conn,
            params=(numero_aviso,)
        )
        conn.close()
        
        if df.empty:
            logger.warning(f"No hay clientes para aviso {numero_aviso}")
            return None
        
        logger.info(f"Obtenidos {len(df)} clientes para aviso {numero_aviso}")
        return df
    except Exception as e:
        logger.error(f"Error obteniendo clientes por aviso: {str(e)}")
        return None


def obtener_zonas_afectadas(numero_aviso: int) -> Optional[pd.DataFrame]:
    """
    Obtiene zonas afectadas desde tabla aviso_zonas_afectadas
    Reemplaza: lectura de provincias_afectadas.csv + distritos_afectados.csv

    Args:
        numero_aviso: Número de aviso

    Returns:
        pd.DataFrame con columnas: departamento, provincia, distrito, area_km2
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "SELECT departamento, provincia, distrito, area_km2 "
            "FROM aviso_zonas_afectadas WHERE numero_aviso = %s "
            "ORDER BY departamento, provincia, distrito",
            (numero_aviso,)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if not rows:
            logger.warning(f"No hay zonas afectadas para aviso {numero_aviso}")
            return None

        df = pd.DataFrame([dict(row) for row in rows])
        logger.info(f"Obtenidas {len(df)} zonas afectadas para aviso {numero_aviso}")
        return df
    except Exception as e:
        logger.error(f"Error obteniendo zonas afectadas: {str(e)}")
        return None


def obtener_estadisticas_aviso(numero_aviso: int) -> Optional[Dict[str, Any]]:
    """
    Obtiene estadísticas consolidadas desde vista v_estadisticas_aviso
    
    Args:
        numero_aviso: Número de aviso
    
    Returns:
        Dict con: total_clientes, clientes_por_nivel, hectareas_por_nivel, etc.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM v_estadisticas_aviso WHERE numero_aviso = %s",
            (numero_aviso,)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not row:
            logger.warning(f"No hay estadísticas para aviso {numero_aviso}")
            return None
        
        cols = [desc[0] for desc in cursor.description]
        stats_dict = dict(zip(cols, row))
        
        logger.info(f"Estadísticas obtenidas para aviso {numero_aviso}")
        return stats_dict
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {str(e)}")
        return None


def obtener_clientes_por_nivel_desde_bd(numero_aviso: int) -> Optional[pd.DataFrame]:
    """
    Obtiene clientes por aviso con nivel como único resultado
    Similar a: lectura de clientes_por_nivel_dia{X}.csv
    
    Args:
        numero_aviso: Número de aviso
    
    Returns:
        pd.DataFrame con TODAS las columnas de v_clientes_por_aviso_completo
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute(
            "SELECT * FROM v_clientes_por_aviso_completo WHERE numero_aviso = %s",
            (numero_aviso,)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not rows:
            logger.warning(f"No hay clientes para aviso {numero_aviso}")
            return None
        
        # Convertir RealDictRows a DataFrame
        df = pd.DataFrame([dict(row) for row in rows])
        
        logger.info(f"Obtenidos {len(df)} clientes desde BD para aviso {numero_aviso}")
        return df
    except Exception as e:
        logger.error(f"Error obteniendo clientes desde BD: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # Para pruebas locales
    logging.basicConfig(level=logging.INFO)
    aviso = obtener_aviso_por_numero(447)
    if aviso:
        print(json.dumps(aviso, default=str, indent=2, ensure_ascii=False))