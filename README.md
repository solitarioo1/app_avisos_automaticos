# 🗺️ APP MAPAS AVISOS SENAMHI

**Sistema automático de generación de mapas meteorológicos para avisos SENAMHI**

Procesa avisos de alerta meteorológica, descarga datos geoespaciales, identifica zonas de riesgo críticas y genera mapas interactivos por departamento, listos para distribución automática.

---

## 🎯 Características Principales

- ✅ **Descarga automática de avisos** desde base de datos PostgreSQL
- ✅ **Procesamiento geoespacial** con GeoPandas + shapefiles SENAMHI
- ✅ **Identificación de día crítico** basada en área de riesgo ALTO
- ✅ **Generación de mapas** (7+ departamentos simultáneamente)
- ✅ **Export WEBP** de alta calidad (optimizado para WhatsApp/mensajería)
- ✅ **API REST Flask** para integración con n8n
- ✅ **Dockerizado** listo para VPS/EasyPanel
- ✅ **Extracción de provincias/distritos** en CSV para análisis

---

## 🏗️ Arquitectura

```
INPUT: JSON Aviso (del BD o archivo)
  ↓
DESCARGA: 1-3 ZIPs con shapefiles diarios (SENAMHI)
  ↓
ANÁLISIS: Calcula área de riesgo por día
  ↓
CRÍTICO: Identifica día con mayor riesgo
  ↓
MAPS: Genera mapas WEBP por departamento afectado
  ↓
OUTPUT: Carpeta con mapas + CSVs → n8n/WhatsApp
```

---

## 📋 Requisitos

- **Python 3.12**
- **PostgreSQL** (opcional, para BD de avisos)
- **Docker + Docker Compose** (para VPS)
- Dependencias: geopandas, matplotlib, flask, psycopg2 (ver `requirements.txt`)

---

## 🚀 Instalación Local

### 1. Clonar repositorio
```bash
git clone https://github.com/TU_USUARIO/APP_MAPAS_AVISOS_SENAMHI.git
cd APP_MAPAS_AVISOS_SENAMHI
```

### 2. Crear entorno virtual
```bash
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate     # Linux/Mac
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Configurar `.env`
```bash
cp .env.example .env  # Si existe, sino crear manualmente
```

Editar `.env` con credenciales reales:
```env
DB_HOST=tu-servidor-bd.com
DB_PORT=5432
DB_NAME=tu_base_datos
DB_USER=tu_usuario
DB_PASSWORD=tu_contraseña
```

### 5. Testear
```bash
# Opción A: Procesar aviso local (JSON/aviso_447.json debe existir)
python procesar_aviso.py 447

# Opción B: Descargar de BD y procesar
python descargar_aviso.py 447 --procesar

# Opción C: Iniciar API Flask
python app.py
# Luego: POST http://localhost:5000/procesar-aviso
```

---

## 🐳 Despliegue con Docker (VPS)

```bash
# Build imagen
docker-compose build

# Iniciar contenedor
docker-compose up -d

# Ver logs
docker-compose logs -f app

# Ejecutar comando dentro del contenedor
docker-compose exec app python procesar_aviso.py 447
```

**Endpoints disponibles:**
- `http://localhost:5000/health` - Verificar salud
- `http://localhost:5000/status` - Estado de directorios
- `POST http://localhost:5000/procesar-aviso` - Disparar procesamiento
- `GET http://localhost:5000/avisos/<numero>` - Consultar resultado

---

## 🔗 Integración n8n

En tu workflow n8n, agregar **HTTP Request Node**:

```json
{
  "method": "POST",
  "url": "http://tu-vps:5000/procesar-aviso",
  "body": {
    "numero_aviso": 447,
    "desde_bd": false
  }
}
```

**Respuesta:**
```json
{
  "status": "success",
  "numero_aviso": 447,
  "output_dir": "/app/OUTPUT/aviso_447",
  "mapas": ["CUSCO.webp", "HUANUCO.webp", "JUNIN.webp", ...],
  "archivos_adicionales": ["provincias_afectadas.csv", "distritos_afectados.csv"]
}
```

Luego, n8n puede descargar los WEBP de `output_dir` y distribuir vía WhatsApp/Email/SMS.

---

## 📁 Estructura de Carpetas

```
APP_MAPAS_AVISOS_SENAMHI/
├── app.py                    # API Flask
├── procesar_aviso.py         # Orquestador principal
├── descargar_aviso.py        # Descarga de BD
├── requirements.txt          # Dependencias Python
├── Dockerfile                # Imagen Docker
├── docker-compose.yml        # Orquestación
├── .env                      # Configuración (sensible, no subir)
├── CONFIG/
│   └── db.py                 # Conexión PostgreSQL
├── LAYOUT/
│   ├── MAPAS.py              # Generador de mapas
│   └── utils.py              # Funciones de procesamiento
├── JSON/                     # Avisos descargados (BD)
├── TEMP/                     # Shapefiles temporales (ZIPs descomprimidos)
├── OUTPUT/                   # Mapas generados (WEBP finales)
├── DELIMITACIONES/           # Shapefiles base (Deptos, Provincias, Distritos)
└── LOGO/                     # Logo SENAMHI
```

---

## 💡 Flujo de Trabajo Típico

### Local (desarrollo)
```bash
python descargar_aviso.py 447 --procesar
# Output: OUTPUT/aviso_447/*.webp listo
```

### VPS + n8n (producción)
```
n8n Trigger → HTTP POST /procesar-aviso → Docker app → OUTPUT
→ n8n descargar WEBP → Distribuir WhatsApp/Email
```

---

## 📊 Salida Típica

```
✓ Aviso 447: NARANJA, duración 53h (3 días)
✓ Día crítico: día2 (172696.40 km²)
✓ Departamentos afectados: 7
✓ Mapas generados:
  - CUSCO.webp
  - HUANUCO.webp
  - JUNIN.webp
  - LORETO.webp
  - MADRE DE DIOS.webp
  - PASCO.webp
  - UCAYALI.webp
✓ Guardado: OUTPUT/aviso_447/
```

---

## 🔧 Configuración Avanzada

### Variables de Entorno (.env)
```env
# Base de datos
DB_HOST=servidor-bd
DB_PORT=5432
DB_NAME=avisos_db
DB_USER=usuario
DB_PASSWORD=contraseña

# Aplicación
FLASK_ENV=production
FLASK_DEBUG=False
FLASK_PORT=5000

# Rutas
TEMP_DIR=TEMP          # Temporales (se limpian)
OUTPUT_DIR=OUTPUT      # Mapas finales (persistentes)
JSON_DIR=JSON          # Avisos descargados
LAYOUT_DIR=LAYOUT      # Scripts de procesamiento
SHP_BASE_DIR=DELIMITACIONES
```

### Limpiar archivos temporales (opcional)
```bash
# Dentro del contenedor
docker-compose exec app rm -rf TEMP/aviso_447
```

---

## 📝 Licencia

Este proyecto es de uso interno para SENAMHI.

---

## 👤 Autor

Desarrollado para automatización de avisos meteorológicos SENAMHI.

---

## 📞 Soporte

Para preguntas o problemas, contactar al equipo de desarrollo.

---

**Última actualización:** 5 de enero de 2026
