# ZeePub Bot - Docker Image

Bot de Telegram para buscar y descargar libros electrónicos en formato EPUB desde catálogos OPDS.

## 🚀 Uso Rápido

1. **Crea un archivo `.env` con tus credenciales**:
```env
TELEGRAM_TOKEN=tu_token_de_botfather
OPDS_URL=https://tu-catalogo-opds.com
MAX_DOWNLOADS=10
WINDOW_HOURS=24
LOG_LEVEL=INFO
```

2. **Crea un archivo `docker-compose.yml`**:
```yaml
version: '3.8'

services:
  zeepub-bot:
    image: devil1210/zeepub-bot:latest
    container_name: zeepub_bot
    restart: always
    env_file:
      - .env
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

3. **Ejecuta el bot**:
```bash
docker-compose up -d
```

## 📋 Variables de Entorno Requeridas

| Variable | Descripción |
|----------|-------------|
| `TELEGRAM_TOKEN` | Token del bot obtenido desde [@BotFather](https://t.me/botfather) |
| `OPDS_URL` | URL del catálogo OPDS |
| `MAX_DOWNLOADS` | Límite de descargas por usuario (opcional, default: 10) |
| `WINDOW_HOURS` | Ventana de tiempo en horas para el límite (opcional, default: 24) |
| `LOG_LEVEL` | Nivel de logging: DEBUG, INFO, WARNING, ERROR (opcional, default: INFO) |

## 🔍 Características

- ✅ Búsqueda de ebooks por palabra clave
- ✅ Navegación en catálogos OPDS
- ✅ Descarga directa de archivos EPUB
- ✅ Límite de descargas por usuario
- ✅ Soporte para chats privados (silencioso en grupos)

## 📚 Documentación Completa

Para más información, visita el [repositorio en GitHub](https://github.com/devil1210/zeepub-bot).

## 🐛 Reportar Problemas

Si encuentras algún error, por favor repórtalo en [GitHub Issues](https://github.com/devil1210/zeepub-bot/issues).

## 📜 Licencia

MIT License
