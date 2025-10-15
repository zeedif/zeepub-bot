# services/__init__.py
from .opds_service import mostrar_colecciones, buscar_zeepubs_directo
from .telegram_service import publicar_libro, send_photo_bytes, send_doc_bytes
from .metadata_service import obtener_metadatos_opds, obtener_sinopsis_opds, obtener_sinopsis_opds_volumen
from .epub_service import parse_opf_from_epub

__all__ = [
    'mostrar_colecciones', 'buscar_zeepubs_directo',
    'publicar_libro', 'send_photo_bytes', 'send_doc_bytes',
    'obtener_metadatos_opds', 'obtener_sinopsis_opds', 'obtener_sinopsis_opds_volumen',
    'parse_opf_from_epub'
]