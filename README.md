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
- **Modo Administrador**:
  - Acceso a bibliotecas restringidas (Evil Mode).
  - Selector de destino para publicar libros en canales o chats específicos.
- **Límites de Descarga**: Sistema de niveles (Lector, VIP, Premium) con cuotas configurables.
- **Arquitectura Moderna**:
  - **Backend**: Python (FastAPI + python-telegram-bot) asíncrono.
  - **Frontend**: React (Vite) servido estáticamente.
  - **Infraestructura**: Docker + Cloudflare Tunnel (sin abrir puertos).
  - **Base de Datos**: Soporte para PostgreSQL y SQLite con gestión de URLs acortadas.
- **Comandos de Administración** (Solo Publishers):
  - `/backup_db`: Genera y envía un backup completo de la base de datos PostgreSQL.
  - `/restore_db`: Restaura la base de datos desde un archivo .sql.
  - `/link_list [limit]`: Lista los links acortados más recientes (hasta 50).
  - `/status_links`: Muestra el estado de los últimos 5 links con validación en tiempo real.
  - `/purge_link <hash>`: Elimina un link acortado específico de la base de datos.
- **Reportes Automáticos**:
  - Sistema de reportes semanales automáticos cada lunes a las 9:00 AM con estadísticas de links (total, válidos, rotos, tasa de éxito).
  - Los reportes se envían automáticamente a todos los publishers configurados.
- **Formato Mejorado de EPUBs**:
  - Extracción avanzada de metadatos con soporte para `epub:type="fulltitle"`.
  - Formato de título completo: `Serie ║ Colección ║ Título Interno`.
  - Preservación de puntuación y subtítulos multilinea.
- **Integración con Facebook**:
  - Preparación automatizada de posts con formato completo (título, metadata, sinopsis, info del archivo).
  - Publicación directa en grupos de Facebook con un solo clic.

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
├── services/                  # Servicios del bot
│   ├── telegram_service.py    # Lógica de envío de EPUBs y FB posts
│   ├── epub_service.py        # Extracción de metadatos y títulos internos
│   ├── opds_service.py        # Navegación de catálogos OPDS
│   └── weekly_reports.py      # Sistema de reportes automáticos semanales
├── utils/                     # Utilidades
│   ├── security.py            # Validación de seguridad (HMAC)
│   ├── url_cache.py           # Gestión de URLs acortadas (SQLite/PostgreSQL)
│   └── url_validator.py       # Validación periódica de links
└── tests/                     # Pruebas unitarias
```

***

## 🛠️ Requisitos

## 📰 Novedades recientes
Resumen breve de los últimos commits del proyecto (noviembre 2025):

- 2025-11-26 (5492770): Nuevo comando `/export_db` que permite a editores exportar la base de datos a CSV.
- 2025-11-26 (4cb2f6f): Comandos de **copia de seguridad** y **restauración** de la base de datos para editores; refactor del formato de publicación de EPUB.
- 2025-11-26 (a52ce5d): Reportes semanales de enlaces para editores; mejoras en generación de nombres de EPUB y limpieza de metadatos; actualización del comando `/purge_link`.
- 2025-11-26 (576b754): Extracción de títulos internos desde EPUB y análisis mejorado de series/volúmenes para generar mensajes más fiables.
- 2025-11-26 (ab5abd8): Soporte para persistencia de URLs con PostgreSQL + SQLAlchemy; validación de enlaces en segundo plano y mejoras en la gestión de la base de datos.
- 2025-11-25 (cff567d): Comandos para debugging y monitorización de links acortados; caché persistente con estadísticas y almacenamiento de títulos.
- 2025-11-25 (9eee15f): Generación y publicación de posts en Facebook con caché persistente de URL corta.
- 2025-11-24 (4332a09): Modo administrador reforzado (OPDS restringido y configuración de usuario), renombrado del servicio a `zeepubs_bot` y mensajes web mejorados.
- 2025-11-24 (7537ae8 / 435c9d9): Inclusión del ID de usuario en la API de configuración y nuevas opciones de destino de publicación.

Estas entradas están pensadas para dar contexto rápido a los contribuyentes — si desea ampliar alguna de ellas con enlaces a PRs o detalles técnicos, puedo añadirlo.

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
ADMIN_USERS=123456789,987654321 # IDs de admins separados por coma

# Cloudflare Tunnel
TUNNEL_TOKEN=eyJhIjoi... (Token obtenido del panel Zero Trust)
PUBLIC_DOMAIN=tu-dominio.com (Ej: bot.midominio.com)

# OPDS
OPDS_SERVER_URL=https://tu-biblioteca-opds.com
OPDS_ROOT_START=/opds-root
OPDS_ROOT_EVIL=/opds-evil # Ruta para administradores

# Configuración
LOG_LEVEL=INFO
MAX_DOWNLOADS_PER_DAY=5

# Publishers (para comandos admin y reportes)
FACEBOOK_PUBLISHERS=123456789,987654321
FACEBOOK_PAGE_ACCESS_TOKEN=tu_token_de_fb
FACEBOOK_GROUP_ID=tu_group_id

# Dominio para links acortados
DL_DOMAIN=https://tu-dominio.com
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
    *   **Service**: `HTTP` -> `zeepubs_bot:8000` (Nota: usa el nombre del servicio Docker, no localhost)

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

## 🧱 Persistencia opcional con Postgres + Alembic

Para entornos de producción recomendamos usar un DBMS gestionado (Postgres) en
vez del SQLite embebido. El proyecto incluye soporte para SQLAlchemy cuando la
variable `DATABASE_URL` está configurada; alembic está incluido para gestionar
las migraciones del esquema de `url_mappings`.

Ejemplo mínimo:

```bash
# en .env
DATABASE_URL=postgresql+psycopg2://zeepub:zeepub@db:5432/zeepub

# crear migraciones (en dev)
pip install -r requirements-dev.txt
alembic -c alembic.ini upgrade head
```

El `docker-compose.yml` del repo añade un servicio `db` (Postgres) y puedes
usar la variable `DATABASE_URL` para que la app use Postgres durante el runtime.