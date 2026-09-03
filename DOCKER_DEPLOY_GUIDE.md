# 🐳 GUÍA DE DOCKERIZACIÓN - APP MAPAS AVISOS SENAMHI

## ✅ CHECKLIST PRE-DEPLOYMENT

Antes de ejecutar Docker, asegúrate de tener:

- [ ] `credentials.json` en la raíz del proyecto (Google Service Account)
- [ ] `.env` configurado correctamente (copia de `.env.docker`)
- [ ] PostgreSQL credenciales actualizadas en `.env`
- [ ] Webhooks n8n actualizados en `.env`
- [ ] `MENSAJERIA_SHEET_ID` correcto en `.env`
- [ ] Google Sheet compartido con `mapas-shet-n8n@n8n-proje-468816.iam.gserviceaccount.com`
- [ ] Docker & Docker Compose instalados

---

## 📋 ESTRUCTURA DEL PROYECTO

```
.
├── Dockerfile                    # Imagen con Python 3.12 + libs geoespaciales
├── docker-compose.yml            # Orquestación Flask + PostgreSQL
├── .dockerignore                 # Archivos a excluir
├── .env                          # Variables de entorno (CREAR DESDE .env.docker)
├── credentials.json              # Google Service Account JSON
├── requirements.txt              # Dependencias Python
├── app.py                        # Flask app principal
├── routes/
│   ├── mensajeria.py            # ✨ Nuevo: Módulo WhatsApp + Google Sheets
│   ├── avisos.py
│   ├── mapas.py
│   └── ...
├── templates/
│   ├── mensajeria.html          # ✨ Nuevo: UI centrada
│   ├── base.html
│   └── ...
├── static/
│   ├── js/mensajeria.js         # ✨ Nuevo: UX mejorada (sin caché)
│   ├── css/mensajeria.css       # ✨ Nuevo: Estilos
│   └── ...
├── DELIMITACIONES/               # Shapefiles (GDAL)
├── JSON/                         # Avisos JSON
├── OUTPUT/                       # Mapas generados (.webp)
├── TEMP/                         # Archivos temporales
└── logs/                         # Logs del contenedor
```

---

## 🚀 INSTRUCCIONES DEPLOYMENT

### 1️⃣ CREAR ARCHIVO .env

Copia `.env.docker` a `.env` y personaliza:

```bash
cp .env.docker .env
```

Luego edita `.env` con tus valores reales:
- `DB_HOST=postgres` (usar 'postgres' para Docker)
- `DB_PASSWORD=AbC&2026_&`
- Webhooks n8n
- `MENSAJERIA_SHEET_ID`

---

### 2️⃣ COPIAR credentials.json

Asegúrate de que `credentials.json` está en la raíz:

```bash
# Verificar
ls -la credentials.json

# Si no existe, cópialo desde tu Google Cloud Console
```

---

### 3️⃣ CONSTRUIR IMAGEN DOCKER

```bash
docker-compose build
```

**Qué hace:**
- Descarga Python 3.12-slim
- Instala libs geoespaciales (GDAL, GEOS, PROJ)
- Instala dependencias Python (geopandas, gspread, flask, etc.)
- Copia código y crea directorios necesarios
- Crea usuario no-root por seguridad

**Tiempo:** ~5-10 minutos (primera vez)

---

### 4️⃣ INICIAR CONTENEDORES

```bash
docker-compose up -d
```

**Qué sucede:**
1. Crea red `app-network`
2. Inicia PostgreSQL (con healthcheck)
3. Inicia Flask (con Gunicorn 4 workers)
4. Monta volúmenes para datos persistentes

**Verificar estado:**
```bash
docker-compose ps
```

Debe mostrar:
```
NAME                        STATUS
mapas-avisos-senamhi        Up (healthy)
mapas-avisos-db             Up (healthy)
```

---

### 5️⃣ VERIFICAR LOGS

```bash
# Ver logs en tiempo real
docker-compose logs -f app

# Ver solo últimas 50 líneas
docker-compose logs -n 50 app
```

Busca mensajes como:
```
🚀 Iniciando servidor Flask - Avisos SENAMHI
Running on http://0.0.0.0:5000
```

---

## ✅ ENDPOINTS DISPONIBLES

Una vez que Docker está corriendo:

```
🏠 Página principal         http://localhost:5000/
📊 Avisos                   http://localhost:5000/avisos
🗺️  Mapas                   http://localhost:5000/mapas
💬 Mensajería               http://localhost:5000/mensajeria/
📋 Historial                http://localhost:5000/mensajeria/historial
❤️  Health check             http://localhost:5000/health
🔍 Status                   http://localhost:5000/status
```

---

## 🔧 COMANDOS ÚTILES

### Ejecutar comando en el contenedor
```bash
# Acceso al shell
docker-compose exec app /bin/bash

# Ejecutar Python
docker-compose exec app python procesar_aviso.py 447
docker-compose exec app python descargar_aviso.py 447 --procesar

# Ver logs de PostgreSQL
docker-compose logs -f postgres
```

### Reiniciar servicios
```bash
# Reiniciar Flask
docker-compose restart app

# Reiniciar PostgreSQL
docker-compose restart postgres

# Reiniciar todo
docker-compose restart
```

### Detener y limpiar
```bash
# Detener sin eliminar volúmenes (datos persistentes)
docker-compose down

# Detener Y eliminar volúmenes (⚠️ BORRA BD)
docker-compose down -v

# Limpiar images/contenedores no usados
docker system prune -a
```

---

## 📁 VOLÚMENES MAPEADOS

| Host | Contenedor | Propósito | Permiso |
|------|-----------|-----------|---------|
| `./JSON` | `/app/JSON` | Avisos JSON origen | RW |
| `./TEMP` | `/app/TEMP` | Archivos temporales | RW |
| `./OUTPUT` | `/app/OUTPUT` | Mapas generados | RW |
| `./DELIMITACIONES` | `/app/DELIMITACIONES` | Shapefiles | RO |
| `./logs` | `/app/logs` | Logs de aplicación | RW |
| `postgres_data` | `/var/lib/postgresql/data` | Datos PostgreSQL | RW |

**Nota:** Los datos en `postgres_data` persisten entre reinicios. Para resetear la BD:
```bash
docker-compose down -v  # ADVERTENCIA: borra todos los datos
docker-compose up -d
```

---

## 🔒 SEGURIDAD

✅ **Implementado:**
- Usuario no-root (`appuser`)
- Variantes de internas (PostgreSQL en red privada)
- Health checks configurados
- Gunicorn (no Flask dev server)

⚠️ **En producción además:**
- Cambiar `DB_PASSWORD` por contraseña fuerte
- Usar reverse proxy (Nginx/Apache) con HTTPS
- Configurar limites de CPU/memoria en docker-compose
- Monitoreo y logs centralizados

---

## 🐛 TROUBLESHOOTING

### Error: "Connection refused" a PostgreSQL
```
Problema: Flask no puede conectar a BD
Solución:
  1. Verificar que postgres está UP: docker-compose ps
  2. Revisar logs: docker-compose logs postgres
  3. Esperar 10 segundos a que inicie PostgreSQL
  4. Reiniciar: docker-compose restart
```

### Error: "Unable to import gspread"
```
Problema: Módulo Python importación falla
Solución:
  1. Verificar requirements.txt tiene gspread y google-auth
  2. Rebuild imagen: docker-compose build --no-cache
  3. Reiniciar: docker-compose up -d
```

### Error: "Webhook no está configurado"
```
Problema: Mensajería no funciona
Solución:
  1. Verificar .env tiene los 4 webhooks N8N
  2. Verificar URLs son correctas en n8n (producción)
  3. Reiniciar Flask: docker-compose restart app
```

### Error: "Permission denied" en TEMP/OUTPUT
```
Problema: No puede escribir archivos
Solución:
  1. Verificar permisos: ls -la TEMP OUTPUT
  2. Asegurar que appuser (UID 1000) puede escribir
  3. Ejecutar en host: chmod -R 755 TEMP OUTPUT
```

---

## 📊 MONITOREO

### Ver recursos usados
```bash
docker stats mapas-avisos-senamhi
```

### Ver métricas de healthcheck
```bash
docker-compose ps
# Si dice "Up (unhealthy)", ver logs para diagnosticar
```

### Backup de base de datos
```bash
docker-compose exec postgres pg_dump -U solitario db_whatsapp > backup.sql
```

### Restore de backup
```bash
docker-compose exec -T postgres psql -U solitario db_whatsapp < backup.sql
```

---

## 🎯 FLUJO COMPLETO

```
1. git clone / git pull
2. cp .env.docker .env
   ↓ Editar .env con valores reales
3. Asegurar credentials.json en raíz
4. docker-compose build
5. docker-compose up -d
6. Esperar 10 seg (PostgreSQL inicia)
7. Acceder a http://localhost:5000
8. Probar /mensajeria endpoint
```

---

## 📞 SOPORTE

Si hay errores en Docker:

1. **Revisar logs:** `docker-compose logs -f`
2. **Verificar .env:** `docker-compose config`
3. **Verificar conectividad:** `docker-compose exec app curl http://postgres:5432`
4. **Rebuild clean:** `docker-compose down && docker-compose build --no-cache && docker-compose up -d`

---

## ✨ NUEVAS CARACTERÍSTICAS EN ESTA VERSION

- ✅ Módulo Mensajería (WhatsApp + Google Sheets)
- ✅ UX mejorada con toasts y progreso
- ✅ Historial sin caché (datos siempre frescos)
- ✅ Contenedor centrado
- ✅ SCOPES Google solo lectura (seguridad)
- ✅ Auto-actualización de historial
- ✅ Configuración Docker lista para producción

---

**Última actualización:** 25/02/2026
**Status:** ✅ Listo para producción
