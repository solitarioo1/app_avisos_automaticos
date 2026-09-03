# ============================================================================
# Dockerfile para APP MAPAS AVISOS SENAMHI
# Imagen Docker con Python 3.12, geopandas y dependencias geoespaciales
# Optimizada para producción en VPS
# ============================================================================

FROM python:3.12-slim

# Establecer variables de entorno
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_ENV=production

# Directorio de trabajo
WORKDIR /app

# ============================================================================
# INSTALAR DEPENDENCIAS DEL SISTEMA
# ============================================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    git \
    build-essential \
    gcc \
    g++ \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    libssl-dev \
    libffi-dev \
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
    pip install gunicorn && \
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
    LOGO \
    logs

# ============================================================================
# CREAR USUARIO NO-ROOT POR SEGURIDAD
# ============================================================================
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# ============================================================================
# EXPONER PUERTO
# ============================================================================
EXPOSE 5000

# ============================================================================
# HEALTH CHECK
# ============================================================================
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/avisos || exit 1

# ============================================================================
# COMANDO POR DEFECTO: GUNICORN PARA PRODUCCIÓN
# ============================================================================
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "4", \
     "--worker-class", "sync", \
     "--timeout", "600", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info", \
     "app:app"]
