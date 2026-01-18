# 📡 APP MAPAS AVISOS SENAMHI - Deployment Guide

Guía completa para subir a GitHub y desplegar en VPS.

---

## 🚀 PASO 1: Preparar para GitHub

### 1.1 Inicializar repositorio Git (si no existe)
```bash
cd /c/Users/20191/OneDrive/Escritorio/PROYECTOS\ POSITIVO/APP_MAPAS_AVISOS_SENAMHI
git init
git add .
git commit -m "Initial commit: APP MAPAS AVISOS SENAMHI"
```

### 1.2 Agregar remoto a GitHub
```bash
git remote add origin https://github.com/TU_USUARIO/APP_MAPAS_AVISOS_SENAMHI.git
git branch -M main
git push -u origin main
```

### 1.3 Crear `.env.production` (NO subir a GitHub)
Crear archivo `.env.production` con variables reales:
```
DB_HOST=tu_servidor.com
DB_PORT=5432
DB_NAME=procesar_aviso
DB_USER=postgres
DB_PASSWORD=tu_contraseña_fuerte
```

⚠️ **Agregar a `.gitignore`:**
```
.env
.env.local
.env.production
```

---

## 🐳 PASO 2: Build de imagen Docker

### 2.1 En local (para pruebas)
```bash
docker build -t mapas-avisos:latest .
docker run -p 5000:5000 mapas-avisos:latest
```

### 2.2 Subir a Docker Hub (opcional pero recomendado)
```bash
# Login a Docker Hub
docker login

# Tagear imagen
docker tag mapas-avisos:latest TU_USUARIO/mapas-avisos:latest

# Push
docker push TU_USUARIO/mapas-avisos:latest
```

---

## 🖥️ PASO 3: Deployment en VPS

### 3.1 Conectarse al VPS
```bash
ssh usuario@tu_vps.com

# O con puerto personalizado
ssh -p 2222 usuario@tu_vps.com
```

### 3.2 Instalar Docker y Docker Compose
```bash
# Instalar Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Instalar Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 3.3 Clonar repositorio
```bash
cd /home/usuario
git clone https://github.com/TU_USUARIO/APP_MAPAS_AVISOS_SENAMHI.git
cd APP_MAPAS_AVISOS_SENAMHI
```

### 3.4 Crear archivo `.env` en VPS
```bash
# Editar .env con datos reales
nano .env

# Pegar:
DB_HOST=postgres
DB_PORT=5432
DB_NAME=procesar_aviso
DB_USER=postgres
DB_PASSWORD=tu_contraseña_fuerte_aqui
FLASK_ENV=production
FLASK_DEBUG=False
```

### 3.5 Levantar contenedores
```bash
# Iniciar servicios
docker-compose up -d

# Ver logs
docker-compose logs -f app

# Ver estado
docker-compose ps
```

---

## ✅ Verificar Deployment

### Healthcheck
```bash
curl http://localhost:5000/avisos
```

### Ver logs en tiempo real
```bash
docker-compose logs -f app
```

### Acceder a la aplicación
```
http://tu_vps.com:5000
```

---

## 📋 Estructura de directorios en VPS

```
/home/usuario/APP_MAPAS_AVISOS_SENAMHI/
├── docker-compose.yml       ← Configuración multi-contenedor
├── Dockerfile               ← Definición imagen Docker
├── .env                     ← Variables de entorno (NO en GitHub)
├── .env.example             ← Plantilla .env (sí en GitHub)
├── app.py                   ← Aplicación Flask
├── procesar_aviso.py        ← Procesador de avisos
├── requirements.txt         ← Dependencias Python
├── DELIMITACIONES/          ← Shapefiles (mapeados en volumen)
├── JSON/                    ← Avisos JSON (volumen persistente)
├── OUTPUT/                  ← Mapas generados (volumen persistente)
├── TEMP/                    ← Archivos temporales (volumen no persistente)
└── logs/                    ← Logs de aplicación
```

---

## 🔒 Seguridad en Producción

### 1. Cambiar contraseña PostgreSQL
```sql
ALTER USER postgres WITH PASSWORD 'nueva_contraseña_fuerte';
```

### 2. Configurar firewall (si es VPS Linux)
```bash
sudo ufw allow 22/tcp
sudo ufw allow 5000/tcp
sudo ufw enable
```

### 3. HTTPS con Let's Encrypt (Recomendado)
```bash
# Instalar certbot
sudo apt-get install certbot python3-certbot-nginx -y

# Generar certificado
sudo certbot certonly --standalone -d tu_dominio.com
```

---

## 🔄 Actualizar código en VPS

```bash
# Entrar al directorio
cd /home/usuario/APP_MAPAS_AVISOS_SENAMHI

# Pull latest code
git pull origin main

# Rebuild imagen
docker-compose build --no-cache

# Reiniciar servicios
docker-compose down
docker-compose up -d

# Ver logs
docker-compose logs -f
```

---

## 🛑 Detener servicios

```bash
# Parar pero mantener datos
docker-compose down

# Eliminar todo incluyendo volúmenes (⚠️ cuidado)
docker-compose down -v
```

---

## 📞 Troubleshooting

### Puerto 5000 ya en uso
```bash
# Ver qué está usando el puerto
lsof -i :5000

# Cambiar puerto en docker-compose.yml
ports:
  - "8000:5000"   # Expone en 8000 externamente
```

### Problema con Base de Datos
```bash
# Verificar conexión
docker-compose exec app python -c "from CONFIG.db import *; print('DB OK')"

# Ver logs de PostgreSQL
docker-compose logs postgres
```

### Limpiar todo
```bash
docker-compose down -v
docker system prune -a
docker volume prune
```

---

## 📊 Monitoreo

### Ver recursos
```bash
docker stats
```

### Ver eventos
```bash
docker-compose events
```

---

**¡Listo! Tu aplicación está en producción en VPS.**
