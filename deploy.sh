#!/bin/bash

# ====================================================================
# Script para facilitar deployment a GitHub y VPS
# ====================================================================

set -e  # Salir si hay error

echo "🚀 APP MAPAS AVISOS SENAMHI - Deployment Script"
echo "=================================================="
echo ""

# Menu
echo "¿Qué deseas hacer?"
echo "1) Subir a GitHub"
echo "2) Build Docker local"
echo "3) Subir a Docker Hub"
echo "4) Ver logs en VPS (SSH)"
echo "5) Actualizar VPS desde GitHub"
echo ""
read -p "Selecciona opción (1-5): " opcion

case $opcion in

  1)
    echo "📤 Subiendo a GitHub..."
    read -p "Ingresa mensaje de commit: " mensaje
    git add .
    git commit -m "$mensaje"
    git push origin main
    echo "✅ Subido a GitHub"
    ;;

  2)
    echo "🐳 Construyendo imagen Docker..."
    docker build -t mapas-avisos:latest .
    echo "✅ Imagen construida: mapas-avisos:latest"
    echo ""
    echo "Para probar localmente:"
    echo "  docker run -p 5000:5000 mapas-avisos:latest"
    ;;

  3)
    echo "🐳 Preparando para Docker Hub..."
    read -p "Usuario Docker Hub: " docker_user
    echo "Taggeando imagen..."
    docker tag mapas-avisos:latest $docker_user/mapas-avisos:latest
    echo "Login a Docker Hub..."
    docker login
    echo "Subiendo imagen..."
    docker push $docker_user/mapas-avisos:latest
    echo "✅ Subido a Docker Hub"
    ;;

  4)
    echo "🖥️  Conectando al VPS..."
    read -p "Usuario VPS: " vps_user
    read -p "IP/Dominio VPS: " vps_host
    read -p "Puerto SSH (default 22): " vps_port
    vps_port=${vps_port:-22}
    
    ssh -p $vps_port $vps_user@$vps_host "cd APP_MAPAS_AVISOS_SENAMHI && docker-compose logs -f app"
    ;;

  5)
    echo "🔄 Actualizando VPS..."
    read -p "Usuario VPS: " vps_user
    read -p "IP/Dominio VPS: " vps_host
    read -p "Puerto SSH (default 22): " vps_port
    vps_port=${vps_port:-22}
    
    ssh -p $vps_port $vps_user@$vps_host << 'EOF'
      cd APP_MAPAS_AVISOS_SENAMHI
      echo "📥 Pull desde GitHub..."
      git pull origin main
      echo "🔨 Rebuilding..."
      docker-compose build --no-cache
      echo "🔄 Reiniciando servicios..."
      docker-compose down
      docker-compose up -d
      echo "✅ VPS Actualizado"
      docker-compose logs -f app
EOF
    ;;

  *)
    echo "❌ Opción inválida"
    exit 1
    ;;

esac

echo ""
echo "✨ Done!"
