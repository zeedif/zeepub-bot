# Zeepub Bot

**Zeepub Bot** es un bot de Telegram avanzado que permite buscar y descargar libros electrónicos en formato EPUB. Integra una **Mini App** (Web App) para una experiencia de usuario moderna, búsqueda por palabra clave, navegación por catálogos OPDS y un sistema robusto de límites de descarga.

***

## 🚀 Características

- **Mini App Integrada**: Interfaz web moderna dentro de Telegram para navegar y descargar.
- **Búsqueda Global**: Busca libros en tu catálogo OPDS directamente desde Telegram.
- **Navegación OPDS**: Explora colecciones, géneros y novedades.
- **Descarga Directa**: Envía archivos EPUB al chat con metadatos enriquecidos (portada, sinopsis, autor).
- **Soporte para Grupos**: Funciona en grupos con topics/forums, respondiendo en el hilo correcto.
- **Seguridad**: Validación criptográfica de `initData` para prevenir suplantación de identidad.
- **Límites de Descarga**: Sistema de niveles (Lector, VIP, Premium) con cuotas configurables.
- **Arquitectura Moderna**:
  - **Backend**: Python (FastAPI + python-telegram-bot) asíncrono.
  - **Frontend**: React (Vite) servido estáticamente.
  - **Infraestructura**: Docker + Cloudflare Tunnel (sin abrir puertos).

***

## 📁 Estructura del Proyecto

```text
├── main.py                    # Punto de entrada (Polling mode - Legacy)
├── run_with_api.py            # Punto de entrada Principal (API + Bot)
├── Dockerfile                 # Construcción Multi-Etapa (Node + Python)
├── docker-compose.yml         # Orquestación (Bot + Cloudflare Tunnel)
├── config/                    # Configuración
│   └── config_settings.py     # Variables de entorno y validación
├── core/                      # Lógica central
│   ├── bot.py                 # Inicialización del bot
│   └── state_manager.py       # Gestión de estado en memoria
├── api/                       # Backend FastAPI
│   ├── routes.py              # Endpoints de la Mini App
│   └── main.py                # Definición de la app FastAPI
├── zeepub-web/                # Frontend React (Mini App)
│   ├── src/                   # Código fuente React
│   └── vite.config.js         # Configuración de build
├── utils/                     # Utilidades
│   └── security.py            # Validación de seguridad (HMAC)
└── tests/                     # Pruebas unitarias
```

***

## 🛠️ Requisitos

- **Docker** y **Docker Compose**
- Token de Telegram (BotFather)
- Token de Cloudflare Tunnel (Zero Trust)
- URL de un catálogo OPDS compatible

***

## 🔧 Instalación y Despliegue

La forma recomendada de desplegar es usando **Docker** y **Cloudflare Tunnel**. Esto garantiza que la Mini App tenga acceso HTTPS seguro sin necesidad de abrir puertos en tu router ni configurar certificados SSL manualmente.

### 1. Clonar el repositorio

```bash
git clone https://github.com/devil1210/zeepub-bot.git
cd zeepub-bot
```

### 2. Configurar Variables de Entorno

Crea un archivo `.env` basado en el ejemplo:

```bash
cp .env.example .env
nano .env
```

**Variables Críticas:**

```env
# Telegram
TELEGRAM_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11

# Cloudflare Tunnel
TUNNEL_TOKEN=eyJhIjoi... (Token obtenido del panel Zero Trust)
PUBLIC_DOMAIN=tu-dominio.com (Ej: bot.midominio.com)

# OPDS
OPDS_SERVER_URL=https://tu-biblioteca-opds.com
OPDS_ROOT_START=/opds-root

# Configuración
LOG_LEVEL=INFO
MAX_DOWNLOADS_PER_DAY=5
```

### 3. Desplegar con Docker

El proyecto usa una construcción multi-etapa. Docker se encargará de:
1.  Compilar el frontend (React) usando Node.js.
2.  Copiar los archivos estáticos al contenedor de Python.
3.  Iniciar el bot y el túnel de Cloudflare.

```bash
docker compose up -d --build
```

### 4. Configurar Cloudflare Tunnel

En tu panel de [Cloudflare Zero Trust](https://one.dash.cloudflare.com/):
1.  Ve a **Access** > **Tunnels**.
2.  Selecciona tu túnel y ve a **Public Hostname**.
3.  Añade un nuevo hostname:
    *   **Public Hostname**: `tu-dominio.com` (El mismo que pusiste en `PUBLIC_DOMAIN`)
    *   **Service**: `HTTP` -> `zeepub_bot:8000` (Nota: usa el nombre del servicio Docker, no localhost)

***

## 🛡️ Seguridad

El bot implementa medidas de seguridad para proteger la API de la Mini App:

- **Validación de `initData`**: El backend verifica la firma criptográfica de Telegram en cada petición (`X-Telegram-Data`). Esto impide que usuarios malintencionados suplanten la identidad de otros.
- **Sin Puertos Expuestos**: Gracias a Cloudflare Tunnel, no es necesario exponer el puerto 8000 a internet. Todo el tráfico entra cifrado por el túnel.

***

## ✅ Tests

El proyecto incluye pruebas unitarias para verificar la API y el comportamiento del bot.

```bash
# Ejecutar tests dentro del contenedor
docker exec zeepub_bot pytest tests/
```

***

## 🤝 Contribuciones

1.  Haz fork del repositorio.
2.  Crea una rama (`git checkout -b feature/nueva-funcion`).
3.  Haz tus cambios y commits.
4.  Envía un Pull Request.

***

## 📜 Licencia

Este proyecto está bajo la licencia **MIT**.