# Etapa 1: Construcción del Frontend
FROM node:18-alpine as frontend-build
WORKDIR /app/frontend
COPY zeepub-web/package*.json ./
RUN npm install
COPY zeepub-web/ ./
RUN npm run build

# Etapa 2: Backend y Bot
FROM python:3.12-slim

WORKDIR /app

# Copiar archivos de requirements y código
COPY requirements.txt ./
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Copiar el frontend construido desde la etapa anterior
COPY --from=frontend-build /app/frontend/dist /app/zeepub-web/dist

# Variables de entorno por defecto (se pueden sobrescribir)
ENV LOG_LEVEL=INFO

# Exponer el puerto de la API
EXPOSE 8000

CMD ["python", "run_with_api.py"]
