# Zeepub Bot

**Zeepub Bot** es un bot de Telegram que permite buscar y descargar libros electrónicos en formato EPUB de manera sencilla y automática. Integra búsqueda por palabra clave, navegación por colecciones OPDS y un sistema de límite de descargas por usuario.

***

## 🚀 Características

- **Búsqueda de ebooks** por palabra clave
- **Navegación** en catálogos OPDS
- **Descarga directa** de archivos EPUB
- **Límite de descargas** por usuario para evitar abusos
- **Arquitectura modular** con plugins
- **Configuración** a través de variables de entorno

***

## 📁 Estructura del proyecto

```text
├── main.py                    # Punto de entrada del bot
├── Dockerfile                 # Configuración de Docker
├── README.md                  # Documentación del proyecto
├── .gitignore                 # Configuración de archivos ignorados
├── config/                    # Configuración del bot
│   ├── config_settings.py
│   └── settings.py
├── core/                      # Núcleo de la lógica
│   ├── bot.py
│   ├── session_manager.py
│   └── state_manager.py
├── handlers/                  # Manejadores de comandos y mensajes
│   ├── callback_handlers.py
│   ├── command_handlers.py
│   └── message_handlers.py
├── opds/                      # Parser OPDS para catálogos
│   ├── helpers.py
│   └── parser.py
├── plugins/                   # Plugins para extender funcionalidades
│   ├── base_plugin.py
│   └── plugin_manager.py
├── services/                  # Servicios (EPUB, metadata, Telegram)
│   ├── epub_service.py
│   └── telegram_service.py
├── utils/                     # Utilidades compartidas
│   ├── decorators.py
│   └── http_client.py
└── tests/                     # Pruebas unitarias
    ├── test_group_behavior.py
    └── tests-init.py
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
    - `OPDS_URL`
    - `MAX_DOWNLOADS`, `WINDOW_HOURS`


***

## ▶️ Uso

Iniciar el bot:

```bash
python main.py
```

- Envía `/start` para ver el menú principal.
- Utiliza `/search <palabra>` para buscar ebooks.
- Descarga directamente desde el chat.

***

## 🐳 Docker

Puedes ejecutar el bot fácilmente usando Docker y Docker Compose.

1.  **Clonar y configurar**:
    ```bash
    git clone https://github.com/devil1210/zeepub-bot.git
    cd zeepub-bot
    cp .env.example .env
    nano .env  # Configura tus variables
    ```

2.  **Ejecutar**:
    Esto construirá la imagen localmente en tu máquina.
    ```bash
    docker-compose up -d --build
    ```

3.  **Ver logs**:
    ```bash
    docker-compose logs -f
    ```

4.  **Detener**:
    ```bash
    docker-compose down
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