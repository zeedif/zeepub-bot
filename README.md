# Zeepub Bot

**Zeepub Bot** es un bot de Telegram que permite buscar y descargar libros electrónicos en formato EPUB de manera sencilla y automática. Integra búsqueda por palabra clave, navegación por colecciones OPDS y un sistema de límite de descargas por usuario.

***

## 🚀 Características

- **Búsqueda de ebooks** por palabra clave (disponible en chats privados y grupos)
- **Navegación** en catálogos OPDS
- **Descarga directa** de archivos EPUB con metadatos enriquecidos
- **Soporte para grupos con topics/forums** - El bot responde en el topic correcto
- **Metadatos EPUB detallados**:
  - Versión EPUB
  - Fecha de modificación (formato DD-MM-YYYY)
  - Fecha de publicación (formato DD-MM-YYYY)
  - Tamaño del archivo
  - Portada embebida
  - Sinopsis y metadatos OPDS
- **Publicación en múltiples destinos** (chats privados, grupos, canales)
- **Límite de descargas** por usuario configurable según nivel (Lector, Patrocinador, VIP, Premium)
- **Arquitectura modular** con plugins
- **Configuración** a través de variables de entorno


***

## 📁 Estructura del proyecto

```text
├── main.py                    # Punto de entrada del bot
├── Dockerfile                 # Configuración de Docker
├── docker-compose.yml         # Orquestación de servicios Docker
├── README.md                  # Documentación del proyecto
├── .gitignore                 # Configuración de archivos ignorados
├── .env.example               # Plantilla de variables de entorno
├── config/                    # Configuración del bot
│   ├── config_settings.py     # Configuración global y niveles de usuario
│   └── settings.py            # Carga de variables de entorno
├── core/                      # Núcleo de la lógica
│   ├── bot.py                 # Inicialización del bot
│   ├── session_manager.py     # Gestión de sesiones y locks
│   └── state_manager.py       # Estado por usuario
├── handlers/                  # Manejadores de comandos y eventos
│   ├── callback_handlers.py  # Callbacks de botones inline
│   ├── command_handlers.py   # Comandos (/start, /help, etc.)
│   └── message_handlers.py   # Mensajes de texto (búsqueda, input)
├── services/                  # Servicios de negocio
│   ├── epub_service.py        # Extracción de metadatos EPUB
│   ├── metadata_service.py    # Procesamiento de metadatos OPDS
│   ├── opds_service.py        # Navegación de catálogos OPDS
│   └── telegram_service.py    # Envío de mensajes, fotos, documentos
├── utils/                     # Utilidades compartidas
│   ├── decorators.py          # Decoradores para autenticación
│   ├── download_limiter.py    # Control de límites de descarga
│   ├── helpers.py             # Funciones auxiliares (URLs, formato, topics)
│   └── http_client.py         # Cliente HTTP y parser de feeds
└── tests/                     # Pruebas unitarias
    └── test_group_behavior.py # Tests de comportamiento en grupos
```



***

## 🛠️ Requisitos

- Python **3.10** o superior
- Token de Telegram (obtenido desde BotFather)
- URL de un catálogo OPDS compatible

***

## 🔧 Instalación

1. Clonar el repositorio:

```bash
git clone https://github.com/devil1210/zeepub-bot.git
cd zeepub-bot
```

2. Crear y activar entorno virtual:

```bash
python3 -m venv venv
source venv/bin/activate
```

3. Instalar dependencias:

```bash
pip install -r requirements.txt
```

4. Configurar variables de entorno:

```bash
cp .env.example .env
nano .env
```

    - `TELEGRAM_TOKEN`
    - `BASE_URL` (URL del Bot)
    - `OPDS_SERVER_URL` (URL del servidor OPDS, opcional)
    - `WEBAPP_URL` (URL de la Mini App, opcional)
    - `OPDS_ROOT_START` (Ruta/Sufijo OPDS inicial)
    - `OPDS_ROOT_EVIL` (Ruta/Sufijo OPDS modo evil)
    - `MAX_DOWNLOADS_PER_DAY`, `WINDOW_HOURS`


***

## ▶️ Uso

Iniciar el bot:

```bash
python main.py
```

### Comandos disponibles

- `/start` - Iniciar el bot y mostrar menú principal
- `/help` - Mostrar ayuda y comandos disponibles
- `/status` - Ver tu nivel de usuario y descargas restantes
- `/cancel` - Cancelar operación actual
- `/search` - Buscar EPUB por palabra clave (solo admins)
- `/plugins` - Listar plugins activos (solo admins)
- `/evil` - Acceso a modo privado con contraseña (solo admins)
- `/reset <user_id>` - Resetear contador de descargas de un usuario (solo admins)

### Uso en grupos

El bot funciona perfectamente en grupos de Telegram:
- **Búsqueda**: Puedes buscar EPUBs desde grupos
- **Topics/Forums**: Si tu grupo tiene topics habilitados, el bot responderá en el topic correcto donde se envió el comando
- **Publicación multi-destino**: Los administradores pueden publicar libros en diferentes canales desde el mismo chat

### Niveles de usuario

El bot soporta diferentes niveles de usuario con límites de descarga configurables:
- **Lector** (`MAX_DOWNLOADS_PER_DAY`): Usuarios normales
- **Patrocinador** (`WHITELIST_DOWNLOADS_PER_DAY`): Usuarios en whitelist
- **VIP** (`VIP_DOWNLOADS_PER_DAY`): Usuarios VIP
- **Premium**: Descargas ilimitadas


***

## 🐳 Docker

Puedes ejecutar el bot fácilmente usando Docker y Docker Compose.

### 🏗️ Construcción y ejecución local

1. **Configurar variables de entorno:**
   ```bash
   cp .env.example .env
   nano .env  # Edita con tu configuración
   ```

2. **Construir y ejecutar:**
   ```bash
   docker-compose up -d --build
   ```

3. **Ver logs:**
   ```bash
   docker-compose logs -f
   ```

4. **Detener:**
   ```bash
   docker-compose down
   ```

### 📦 Compartir imagen entre máquinas

Si quieres mover la imagen construida a otra máquina sin reconstruir:

1. **Guardar imagen en un archivo:**
   ```bash
   docker save -o zeepub_bot.tar zeepub_bot_zeepub-bot
   ```

2. **Copiar el archivo** `zeepub_bot.tar` a la otra máquina usando `scp` o USB.

3. **Cargar imagen en la máquina destino:**
   ```bash
   docker load -i zeepub_bot.tar
   ```

4. **Ejecutar:**
   ```bash
   docker-compose up -d
   ```
   
   Asegúrate de tener tu archivo `.env` configurado en la máquina destino.

### 🔄 Actualizar el bot

Para actualizar a la última versión:

```bash
git pull
docker-compose up -d --build
```


***

## ✅ Tests

Ejecutar pruebas unitarias:

```bash
pytest tests/
```


***

## ⚙️ Plugins y Personalización

1. Crear nuevo plugin en `plugins/` heredando de `BasePlugin`.
2. Registrar en `plugins/plugin_manager.py`.
3. Ajustar o añadir handlers y servicios según la funcionalidad.

***

## 🤝 Contribuciones

1. Haz fork del repo.
2. Crea una rama:

```bash
git checkout -b feature/tu-funcion
```

3. Realiza cambios y añade pruebas.
4. Envía un Pull Request describiendo tus mejoras.

***

## 📜 Licencia

Este proyecto está bajo la licencia **MIT**. Consulte el archivo `LICENSE` para más detalles.