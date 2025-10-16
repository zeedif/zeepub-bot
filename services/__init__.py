# services/__init__.py

# Servicios principales del bot

from .opds_service import mostrar_colecciones, buscar_zeepubs_directo
from .metadata_service import (
    obtener_sinopsis_opds,
    obtener_sinopsis_opds_volumen,
    obtener_metadatos_opds,
)
from .telegram_service import send_photo_bytes, send_doc_bytes, publicar_libro
from .epub_service import parse_opf_from_epub

__all__ = [
    "mostrar_colecciones",
    "buscar_zeepubs_directo",
    "obtener_sinopsis_opds",
    "obtener_sinopsis_opds_volumen",
    "obtener_metadatos_opds",
    "send_photo_bytes",
    "send_doc_bytes",
    "publicar_libro",
    "parse_opf_from_epub",
]
