# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copiar archivos de requirements y código
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Variables de entorno por defecto (se pueden sobrescribir)
ENV LOG_LEVEL=INFO

# Exponer el puerto de la API
EXPOSE 8000

CMD ["python", "run_with_api.py"]
