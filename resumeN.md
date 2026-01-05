# Resumen pasado de la APP pero algunos datos pero falta modificarrr

## Objetivo General
Sistema automatizado que procesa avisos meteorológicos del SENAMHI, genera mapas de riesgo por departamento y envía alertas personalizadas por WhatsApp a agricultores según ubicación GPS de sus cultivos.

---

## Arquitectura del Sistema

### 1. Componentes Principales
- **n8n**: Orquestación del flujo (scraping, filtrado, activación, envíos)
- **App Python (Docker)**: Procesamiento geoespacial y generación de mapas
- **PostgreSQL**: Almacenamiento de avisos, clientes, cultivos y resultados
- **VPS**: Hosting (12GB RAM - suficiente)
- **Evolution API**: Envío masivo de WhatsApp

---

## Flujo de Trabajo Completo

### Fase 1: Captura y Filtrado (n8n)
1. **Scraping cada 12 horas** del SENAMHI
2. **Extrae avisos** en formato ZIP (cada aviso = 3 días, 3 ZIPs con SHP)
3. **Filtro automático**: Solo procesa avisos nivel **ROJO** o **NARANJA**
4. Si pasa filtro → activa App Python

### Fase 2: Procesamiento (App Python)
**Input**: 3 ZIPs con archivos SHP (polígonos de riesgo para todo Perú)

**Proceso**:
1. Lee los 3 SHP (1 por día del evento)
2. Identifica departamentos afectados (ej: CUSCO, PUNO, JUNIN...)
3. **Selecciona el día más crítico** (mayor área roja/naranja o más provincias afectadas)
4. **Fragmenta SHP general** por departamento
5. **Genera mapas PNG** (1 por departamento afectado):
   - Departamento con delimitación interna de provincias
   - Colores: ROJO > NARANJA > AMARILLO
   - Alta resolución (formato PNG)
6. **Validación GPS**: Point-in-polygon (geopandas)
   - Cruza GPS de clientes contra polígonos de riesgo
   - Determina qué clientes están en zona afectada
7. **Guarda resultados**:
   - Imágenes: `/var/www/imagenes/avisos/aviso_001/`
   - Metadata en Postgres: `aviso_id, departamento, nivel_riesgo, ruta_imagen`
   - Clientes afectados: `cliente_id, aviso_id, nivel_riesgo, enviar=true`

**Output**: JSON con clientes afectados + rutas de mapas

**Tiempo estimado**: 10 minutos por aviso

### Fase 3: Envío Personalizado (n8n)
1. Recibe JSON de la App Python
2. Procesa **por lotes** (evitar detección WhatsApp)
3. Para cada cliente afectado:
   - Personaliza mensaje: "Juan, cuidado con tu cultivo de papa en Cusco, entre hoy y mañana habrá granizada..."
   - Adjunta mapa PNG del departamento
   - Envía vía Evolution API

---

## Datos Técnicos

### Base de Datos (PostgreSQL)
**Tablas existentes**:
- `clientes`: GPS, departamento, provincia, distrito, cultivos, costo_estimado

**Tablas nuevas**:
- `avisos`: id, numero_aviso, fecha_inicio, fecha_fin, departamentos_afectados
- `avisos_mapas`: aviso_id, departamento, nivel_riesgo, ruta_imagen
- `clientes_afectados`: cliente_id, aviso_id, nivel_riesgo, enviar (bool)

### Conexión n8n ↔ App Python
**Nodo**: HTTP Request (POST sincrónico)
- n8n envía: `{aviso_id: "001", zips: [urls...]}`
- App procesa (espera 10 min)
- App responde: `{clientes_afectados: [...], mapas: [...]}`

### Especificaciones App Python
- **Librerías**: geopandas, matplotlib, shapely, rasterio
- **Imagen Docker**: ~1-1.5GB
- **RAM necesaria**: 512MB-2GB por ejecución
- **Endpoint**: `POST /procesar-aviso`

---

## Visualización Secundaria (Power BI)
- Conecta a Postgres
- Dashboard automático:
  - Personas afectadas por evento
  - Costos estimados por cultivo/región
  - Histórico de avisos
- Actualización automática al ingresar nuevos avisos

---

## Despliegue

### GitHub
```
repo/
├── Dockerfile
├── docker-compose.yml
├── app/
│   ├── main.py (API Flask/FastAPI)
│   ├── procesar_shp.py
│   ├── generar_mapas.py
│   └── validar_gps.py
├── requirements.txt
└── README.md
```

### Easypanel
1. Conectar repo de GitHub
2. Build automático de Docker
3. Exponer puerto de API
4. n8n consume URL: `https://tu-app.easypanel.host/procesar-aviso`

---

## Próximos Pasos
1. ✅ Analizar estructura de SHP de ejemplo (columnas, niveles)
2. ✅ Crear prototipo de API Python
3. ✅ Generar primer mapa manual (definir modelo visual)
4. ✅ Dockerizar aplicación
5. ✅ Integrar con n8n (pruebas de flujo completo)
6. ✅ Deploy en Easypanel
7. ✅ Configurar envíos por lotes en WhatsApp

---

## Notas Importantes
- **Filtro previo**: Solo ROJO/NARANJA reduce carga ~70%
- **Validación GPS**: Más precisa que cruce por distrito
- **Mapas**: 1 por departamento, día más crítico
- **Lotes WhatsApp**: Evitar saturación/detección
- **VPS 12GB RAM**: Más que suficiente para 15k clientes