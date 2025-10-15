import importlib.util
import inspect
from pathlib import Path
from typing import Dict
import logging
from plugins.base_plugin import BasePlugin


class PluginManager:
    def __init__(self, plugin_directory: str = "plugins"):
        self.plugin_directory = Path(plugin_directory)
        self.plugins: Dict[str, BasePlugin] = {}

    async def initialize(self, bot_instance):
        self._bot_instance = bot_instance
        await self.load_all_plugins()

    async def load_all_plugins(self):
        if not self.plugin_directory.exists():
            logging.warning(f"Directorio de plugins no existe: {self.plugin_directory}")
            return

        for plugin_file in self.plugin_directory.glob("*.py"):
            if plugin_file.name in ["__init__.py", "base_plugin.py", "plugin_manager.py"]:
                continue
            try:
                await self.load_plugin(plugin_file)
            except Exception as e:
                logging.error(f"Error cargando plugin {plugin_file.name}: {e}")

    async def load_plugin(self, plugin_path: Path):
        spec = importlib.util.spec_from_file_location(plugin_path.stem, plugin_path)
        if not spec or not spec.loader:
            logging.error(f"No se pudo obtener spec para el plugin {plugin_path.name}")
            return

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        plugin_classes = [
            cls for name, cls in inspect.getmembers(module, inspect.isclass)
            if issubclass(cls, BasePlugin) and cls is not BasePlugin
        ]

        if not plugin_classes:
            logging.warning(f"No se encontraron clases de plugin válidas en {plugin_path.name}")
            return

        plugin_instance = plugin_classes[0]()
        initialized = await plugin_instance.initialize(self._bot_instance)

        if initialized:
            self.plugins[plugin_instance.name] = plugin_instance
            logging.info(f"Plugin cargado: {plugin_instance.name} v{plugin_instance.version}")
        else:
            logging.warning(f"Inicialización fallida para plugin {plugin_instance.name}")

    def list_plugins(self):
        return {
            name: {
                "version": plugin.version,
                "description": plugin.description
            }
            for name, plugin in self.plugins.items()
        }
