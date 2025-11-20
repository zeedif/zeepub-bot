#!/bin/bash
set -e

IMAGE_NAME="devil1210/zeepub-bot:latest"

echo "🐳 Construyendo imagen: $IMAGE_NAME..."
docker build -t $IMAGE_NAME .

echo "🚀 Subiendo a Docker Hub..."
docker push $IMAGE_NAME

echo "✅ ¡Listo! Imagen actualizada en la nube."
