# ============================================================================
# Dockerfile para APP MAPAS AVISOS SENAMHI
# Imagen Docker con Python 3.12, geopandas y dependencias geoespaciales
# ============================================================================

FROM python:3.12-slim

# Establecer variables de entorno
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Directorio de trabajo
WORKDIR /app

# ============================================================================
# INSTALAR DEPENDENCIAS DEL SISTEMA
# ============================================================================
# Necesarias para geopandas, shapely, GDAL, PROJ, etc.

RUN apt-get update && apt-get install -y --no-install-recommends \
    # Utilidades
    curl \
    wget \
    git \
    # Compiladores
    build-essential \
    gcc \
    g++ \
    # GDAL y dependencias geoespaciales
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    # Otras librerías
    libssl-dev \
    libffi-dev \
    # Limpiar cache
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ============================================================================
# VARIABLES DE ENTORNO PARA GDAL
# ============================================================================
ENV GDAL_CONFIG=/usr/bin/gdal-config \
    CPLUS_INCLUDE_PATH=/usr/include/gdal \
    C_INCLUDE_PATH=/usr/include/gdal

# ============================================================================
# INSTALAR DEPENDENCIAS DE PYTHON
# ============================================================================
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# ============================================================================
# COPIAR CÓDIGO DE LA APLICACIÓN
# ============================================================================
COPY . .

# ============================================================================
# CREAR DIRECTORIOS NECESARIOS
# ============================================================================
RUN mkdir -p \
    JSON \
    TEMP \
    OUTPUT \
    LAYOUT \
    CONFIG \
    DELIMITACIONES \
    LOGO

# ============================================================================
# EXPONER PUERTO
# ============================================================================
EXPOSE 5000

# ============================================================================
# HEALTH CHECK
# ============================================================================
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# ============================================================================
# COMANDO POR DEFECTO: INICIAR API FLASK CON GUNICORN
# ============================================================================
# Para producción, usar gunicorn. Para desarrollo, comentar y usar Flask directamente.
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "2", \
     "--timeout", "600", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]

# ============================================================================
# ALTERNATIVAS DE COMANDO:
# ============================================================================
# Para ejecutar solo procesar_aviso.py:
# CMD ["python", "procesar_aviso.py", "447"]
#
# Para ejecutar API en modo desarrollo (debug=True):
# CMD ["python", "app.py"]
#
# Para ejecutar descargar_aviso.py + procesar:
# CMD ["python", "descargar_aviso.py", "447", "--procesar"]
