# services/telegram_service.py

import io
import os
import logging
from urllib.parse import urlparse, unquote
from telegram import InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from core.state_manager import state_manager
from core.session_manager import session_manager
from config.config_settings import config
from services.metadata_service import (
    obtener_metadatos_opds,
    obtener_sinopsis_opds,
    obtener_sinopsis_opds_volumen,
)
from services.epub_service import parse_opf_from_epub
from utils.http_client import fetch_bytes, cleanup_tmp
from utils.helpers import (
    generar_slug_from_meta,
    formatear_mensaje_portada,
    escapar_html,
)
from utils.download_limiter import record_download, can_download, downloads_left
from services.epub_service import parse_opf_from_epub, extract_cover_from_epub

logger = logging.getLogger(__name__)


async def send_photo_bytes(
    bot,
    chat_id,
    caption,
    data_or_path,
    filename="cover.jpg",
    parse_mode=None,
    message_thread_id=None,
):
    """Envía imagen desde bytes o ruta de archivo."""
    if not data_or_path:
        return None
    try:
        if isinstance(data_or_path, (bytes, bytearray)):
            bio = io.BytesIO(data_or_path)
            bio.name = filename
            bio.seek(0)
            input_file = InputFile(bio, filename=filename)
            try:
                return await bot.send_photo(
                    chat_id=chat_id,
                    photo=input_file,
                    caption=caption,
                    parse_mode=parse_mode,
                    message_thread_id=message_thread_id,
                )
            except BadRequest as e:
                if (
                    "Message thread not found" in str(e)
                    and message_thread_id is not None
                ):
                    # Retry without thread_id (send to General/Main)
                    bio.seek(0)
                    return await bot.send_photo(
                        chat_id=chat_id,
                        photo=input_file,
                        caption=caption,
                        parse_mode=parse_mode,
                        message_thread_id=None,
                    )
                raise e

        elif isinstance(data_or_path, str) and os.path.exists(data_or_path):
            # Read image file asynchronously into memory (covers are small)
            try:
                import aiofiles

                data_bytes = None
                async with aiofiles.open(data_or_path, "rb") as af:
                    data_bytes = await af.read()
                if data_bytes is not None:
                    bio = io.BytesIO(data_bytes)
                    bio.name = filename
                    bio.seek(0)
                    input_file = InputFile(bio, filename=filename)
                    try:
                        return await bot.send_photo(
                            chat_id=chat_id,
                            photo=input_file,
                            caption=caption,
                            parse_mode=parse_mode,
                            message_thread_id=message_thread_id,
                        )
                    except BadRequest as e:
                        if (
                            "Message thread not found" in str(e)
                            and message_thread_id is not None
                        ):
                            bio.seek(0)
                            return await bot.send_photo(
                                chat_id=chat_id,
                                photo=input_file,
                                caption=caption,
                                parse_mode=parse_mode,
                                message_thread_id=None,
                            )
                        raise e
            except Exception:
                # Fallback to synchronous open if aiofiles fails
                with open(data_or_path, "rb") as f:
                    input_file = InputFile(f, filename=filename)
                    try:
                        return await bot.send_photo(
                            chat_id=chat_id,
                            photo=input_file,
                            caption=caption,
                            parse_mode=parse_mode,
                            message_thread_id=message_thread_id,
                        )
                    except BadRequest as e:
                        if (
                            "Message thread not found" in str(e)
                            and message_thread_id is not None
                        ):
                            f.seek(0)
                            return await bot.send_photo(
                                chat_id=chat_id,
                                photo=input_file,
                                caption=caption,
                                parse_mode=parse_mode,
                                message_thread_id=None,
                            )
                        raise e
    except Exception as e:
        logger.debug(f"Error send_photo_bytes: {e}")
    return None


async def send_doc_bytes(
    bot,
    chat_id,
    caption,
    data_or_path,
    filename="file.epub",
    parse_mode=None,
    message_thread_id=None,
):
    """Envía documento EPUB desde bytes o ruta de archivo."""
    if not data_or_path:
        return None
    try:
        if isinstance(data_or_path, (bytes, bytearray)):
            bio = io.BytesIO(data_or_path)
            bio.name = filename
            bio.seek(0)
            input_file = InputFile(bio, filename=filename)
            try:
                return await bot.send_document(
                    chat_id=chat_id,
                    document=input_file,
                    caption=caption,
                    parse_mode=parse_mode,
                    message_thread_id=message_thread_id,
                )
            except BadRequest as e:
                if (
                    "Message thread not found" in str(e)
                    and message_thread_id is not None
                ):
                    bio.seek(0)
                    return await bot.send_document(
                        chat_id=chat_id,
                        document=input_file,
                        caption=caption,
                        parse_mode=parse_mode,
                        message_thread_id=None,
                    )
                raise e
        elif isinstance(data_or_path, str) and os.path.exists(data_or_path):
            # Decide whether to load to memory or stream from disk
            try:
                import asyncio as _asyncio

                size = await _asyncio.to_thread(os.path.getsize, data_or_path)
            except Exception:
                size = None

            if size is not None and size <= config.MAX_IN_MEMORY_BYTES:
                # Small file: read async into memory then send
                try:
                    import aiofiles

                    async with aiofiles.open(data_or_path, "rb") as af:
                        data_read = await af.read()
                    bio = io.BytesIO(data_read)
                    bio.name = filename
                    bio.seek(0)
                    input_file = InputFile(bio, filename=filename)
                    try:
                        return await bot.send_document(
                            chat_id=chat_id,
                            document=input_file,
                            caption=caption,
                            parse_mode=parse_mode,
                            message_thread_id=message_thread_id,
                        )
                    except BadRequest as e:
                        if (
                            "Message thread not found" in str(e)
                            and message_thread_id is not None
                        ):
                            bio.seek(0)
                            return await bot.send_document(
                                chat_id=chat_id,
                                document=input_file,
                                caption=caption,
                                parse_mode=parse_mode,
                                message_thread_id=None,
                            )
                        raise e
                except Exception:
                    pass

            # Large file: open synchronously (cheap) and let telegram lib stream it
            with open(data_or_path, "rb") as f:
                input_file = InputFile(f, filename=filename)
                try:
                    return await bot.send_document(
                        chat_id=chat_id,
                        document=input_file,
                        caption=caption,
                        parse_mode=parse_mode,
                        message_thread_id=message_thread_id,
                    )
                except BadRequest as e:
                    if (
                        "Message thread not found" in str(e)
                        and message_thread_id is not None
                    ):
                        f.seek(0)
                        return await bot.send_document(
                            chat_id=chat_id,
                            document=input_file,
                            caption=caption,
                            parse_mode=parse_mode,
                            message_thread_id=None,
                        )
                    raise e
    except Exception as e:
        logger.debug(f"Error send_doc_bytes: {e}")
    return None


async def publicar_libro(
    update,
    context: ContextTypes.DEFAULT_TYPE,
    uid: int,
    titulo: str,
    portada_url: str,
    epub_url: str,
    menu_prep: tuple = None,
):
    """Descarga EPUB para metadatos, muestra portada, sinopsis y botones."""
    bot = context.bot
    user_state = state_manager.get_user_state(uid)
    lock = session_manager.get_publish_lock(uid)

    async with lock:
        from utils.helpers import get_thread_id

        thread_id_origen = get_thread_id(update)

        destino = user_state.get("destino") or update.effective_chat.id
        chat_origen = user_state.get("chat_origen") or destino
        series_id = user_state.get("series_id")
        volume_id = user_state.get("volume_id")
        user_state["ultima_pagina"] = user_state.get("url", config.OPDS_ROOT_START)

        # Solo usar thread_id si destino == chat_origen
        thread_id_destino = thread_id_origen if destino == chat_origen else None

        # Verificar límite antes de descargar
        if not can_download(uid):
            await bot.send_message(
                chat_id=destino,
                text="🚫 Has alcanzado tu límite de descargas por hoy.",
                message_thread_id=thread_id_destino,
            )
            return

        # Obtener metadatos OPDS
        meta = await obtener_metadatos_opds(series_id, volume_id)

        # Descargar EPUB para parsear metadatos
        epub_downloaded = None
        if epub_url:
            epub_downloaded = await fetch_bytes(epub_url, timeout=120)
            if epub_downloaded:
                # Use centralized metadata enrichment
                from services.epub_service import enrich_metadata_from_epub

                meta = await enrich_metadata_from_epub(epub_downloaded, epub_url, meta)

                # Guardar EPUB y metadatos para envío posterior
                user_state["epub_buffer"] = epub_downloaded
                user_state["epub_url"] = epub_url
                user_state["meta_pendiente"] = meta

        # Store pending portada and title so callback flows can continue
        user_state["portada_pendiente"] = portada_url
        user_state["titulo_pendiente"] = titulo

        logger.debug(
            "publicar_libro called uid=%s titulo=%r destino=%s chat_origen=%s",
            uid,
            titulo,
            destino,
            chat_origen,
        )

        # Borrar mensaje "Preparando..." si existe
        if menu_prep:
            try:
                await bot.delete_message(chat_id=menu_prep[0], message_id=menu_prep[1])
            except Exception as e:
                logger.debug("No se pudo borrar mensaje 'Preparando...': %s", e)

        # For publishers the choice is asked earlier; just continue publishing normally

        # Dentro de publicar_libro, donde quieras enviar portada:
        mensaje_portada = formatear_mensaje_portada(meta)

        # Extraer portada embebida
        cover_bytes = None
        if epub_downloaded:
            cover_bytes = extract_cover_from_epub(epub_downloaded)

        # Fallback a URL OPDS
        if cover_bytes:
            portada_data = cover_bytes
        else:
            portada_data = await fetch_bytes(portada_url, timeout=15)

        await send_photo_bytes(
            bot,
            destino,
            mensaje_portada,
            portada_data,
            filename="cover.jpg",
            parse_mode="HTML",
            message_thread_id=thread_id_destino,
        )

        if not cover_bytes:
            cleanup_tmp(portada_data)

        # Sinopsis
        sinopsis = meta.get("sinopsis")
        if not sinopsis:
            if series_id and volume_id:
                sinopsis = await obtener_sinopsis_opds_volumen(series_id, volume_id)
            if not sinopsis and series_id:
                try:
                    sinopsis = await obtener_sinopsis_opds(series_id)
                except Exception as e:
                    logger.error(f"Error sinopsis OPDS: {e}")

        if sinopsis:
            sinopsis_esc = escapar_html(sinopsis)
            texto = f"<b>Sinopsis:</b>\n<blockquote>{sinopsis_esc}</blockquote>\n#{generar_slug_from_meta(meta)}"
            try:
                await bot.send_message(
                    chat_id=destino,
                    text=texto,
                    parse_mode="HTML",
                    message_thread_id=thread_id_destino,
                )
            except BadRequest as e:
                if (
                    "Message thread not found" in str(e)
                    and thread_id_destino is not None
                ):
                    await bot.send_message(
                        chat_id=destino,
                        text=texto,
                        parse_mode="HTML",
                        message_thread_id=None,
                    )
                else:
                    raise e
        else:
            slug = generar_slug_from_meta(meta)
            fallback = (
                f"Sinopsis: (no disponible)\n#{slug}"
                if slug
                else "Sinopsis: (no disponible)"
            )
            try:
                await bot.send_message(
                    chat_id=destino, text=fallback, message_thread_id=thread_id_destino
                )
            except BadRequest as e:
                if (
                    "Message thread not found" in str(e)
                    and thread_id_destino is not None
                ):
                    await bot.send_message(
                        chat_id=destino, text=fallback, message_thread_id=None
                    )
                else:
                    raise e

        # Mostrar botones
        # Calcular tamaño y versión para el mensaje de confirmación
        if epub_downloaded:
            # Calcular tamaño: fetch_bytes puede devolver bytes o ruta de archivo
            if isinstance(epub_downloaded, (bytes, bytearray)):
                size_mb = len(epub_downloaded) / (1024 * 1024)
            elif isinstance(epub_downloaded, str) and os.path.exists(epub_downloaded):
                size_mb = os.path.getsize(epub_downloaded) / (1024 * 1024)
            else:
                size_mb = 0.0

            version = meta.get("epub_version", "2.0")
            fecha = meta.get("fecha_modificacion", "Desconocida")
            titulo_vol = meta.get("titulo_volumen") or titulo or "Desconocido"

            info_text = (
                f"📂 <b>{titulo_vol}</b>\n"
                f"ℹ️ Versión Epub: {version}\n"
                f"📅 Actualizado: {fecha}\n"
                f"📦 Tamaño: {size_mb:.2f} MB"
            )

            # Enviar mensaje de información separado (siempre en chat_origen con thread_id)
            # Enviar mensaje de información separado (siempre en chat_origen con thread_id)
            try:
                msg_info = await bot.send_message(
                    chat_id=chat_origen,
                    text=info_text,
                    parse_mode="HTML",
                    message_thread_id=thread_id_origen,
                )
            except BadRequest as e:
                if (
                    "Message thread not found" in str(e)
                    and thread_id_origen is not None
                ):
                    msg_info = await bot.send_message(
                        chat_id=chat_origen,
                        text=info_text,
                        parse_mode="HTML",
                        message_thread_id=None,
                    )
                else:
                    raise e
            user_state["msg_info_id"] = msg_info.message_id

        keyboard = [
            [
                InlineKeyboardButton("📥 Descargar", callback_data="descargar_epub"),
                InlineKeyboardButton("↩️ Volver", callback_data="volver_ultima"),
            ],
        ]

        try:
            sent = await bot.send_message(
                chat_id=chat_origen,
                text="¿Deseas descargar este EPUB?",
                parse_mode="HTML",
                message_thread_id=thread_id_origen,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except BadRequest as e:
            if "Message thread not found" in str(e) and thread_id_origen is not None:
                sent = await bot.send_message(
                    chat_id=chat_origen,
                    text="¿Deseas descargar este EPUB?",
                    parse_mode="HTML",
                    message_thread_id=None,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            else:
                raise e
        user_state["msg_botones_id"] = sent.message_id
        user_state["titulo_pendiente"] = titulo


async def descargar_epub_pendiente(
    update, context: ContextTypes.DEFAULT_TYPE, uid: int
):
    """Envía el EPUB guardado tras confirmación del usuario."""
    bot = context.bot
    user_state = state_manager.get_user_state(uid)

    from utils.helpers import get_thread_id

    thread_id_origen = user_state.get(
        "message_thread_id"
    )  # Usar el guardado en el estado

    epub_buffer = user_state.pop("epub_buffer", None)
    epub_url = user_state.pop("epub_url", "")
    meta = user_state.pop("meta_pendiente", {})
    titulo = user_state.pop("titulo_pendiente", "")
    msg_id = user_state.pop("msg_botones_id", None)
    msg_info_id = user_state.pop("msg_info_id", None)
    destino = user_state.get("destino") or update.effective_chat.id
    chat_origen = user_state.get("chat_origen") or destino

    # Solo usar thread_id si destino == chat_origen
    thread_id_destino = thread_id_origen if destino == chat_origen else None

    # Borrar botones y mensaje de info
    if msg_id:
        try:
            await bot.delete_message(chat_id=chat_origen, message_id=msg_id)
        except Exception as e:
            logger.debug("Could not delete msg_id %s: %s", msg_id, e)
    if msg_info_id:
        try:
            await bot.delete_message(chat_id=chat_origen, message_id=msg_info_id)
        except Exception as e:
            logger.debug("Could not delete msg_info_id %s: %s", msg_info_id, e)

    # Si eligió Volver, descartar buffer
    if update.callback_query.data == "volver_ultima":
        return

    # Verificar que hay EPUB disponible
    if not epub_buffer:
        await bot.send_message(
            chat_id=chat_origen,
            text="⚠️ EPUB no disponible.",
            message_thread_id=thread_id_origen,
        )
        return

    # Verificar cuota nuevamente
    if not can_download(uid):
        await bot.send_message(
            chat_id=destino,
            text="🚫 Límite de descargas alcanzado.",
            message_thread_id=thread_id_destino,
        )
        return

    # Preparar envío
    prep = await bot.send_message(
        chat_id=destino,
        text="⏳ Preparando archivo...",
        message_thread_id=thread_id_destino,
    )

    try:
        # Enviar EPUB
        fname = unquote(urlparse(epub_url).path.split("/")[-1]) or "archivo.epub"

        # Calcular tamaño: epub_buffer puede ser bytes o ruta de archivo
        if isinstance(epub_buffer, (bytes, bytearray)):
            size_mb = len(epub_buffer) / (1024 * 1024)
        elif isinstance(epub_buffer, str) and os.path.exists(epub_buffer):
            size_mb = os.path.getsize(epub_buffer) / (1024 * 1024)
        else:
            size_mb = 0.0
        version = meta.get("epub_version", "2.0")  # Default a 2.0 si no se encuentra
        fecha = meta.get("fecha_modificacion", "Desconocida")
        titulo_vol = meta.get("titulo_volumen") or titulo or "Desconocido"

        caption = (
            f"📂 <b>{titulo_vol}</b>\n"
            f"ℹ️ Versión Epub: {version}\n"
            f"📅 Actualizado: {fecha}\n"
            f"📦 Tamaño: {size_mb:.2f} MB"
        )

        slug = generar_slug_from_meta(meta)
        if slug:
            caption += f"\n#{slug}"

        sent_doc = await send_doc_bytes(
            bot,
            destino,
            caption,
            epub_buffer,
            filename=fname,
            parse_mode="HTML",
            message_thread_id=thread_id_destino,
        )

        if sent_doc:
            # Log to history
            from services.history_service import log_published_book
            # file_info construction
            file_info = {
                "file_size": sent_doc.document.file_size,
                "file_unique_id": sent_doc.document.file_unique_id
            }
            # Run in background or await? It's sync db op, maybe run in thread or make it async?
            # The service uses sqlalchemy sync engine. Better to run in thread if possible, or just call it if it's fast.
            # For now, just call it. SQLite is fast.
            try:
                log_published_book(
                    meta=meta,
                    message_id=sent_doc.message_id,
                    channel_id=sent_doc.chat.id,
                    file_info=file_info
                )
            except Exception as e:
                logger.error(f"Failed to log book history: {e}")

        # Registrar descarga
        record_download(uid)
        restantes = downloads_left(uid)

        # Mostrar descargas restantes (excepto Premium)
        if restantes != "ilimitadas":
            await bot.send_message(
                chat_id=destino,
                text=f"📥 Te quedan {restantes} descargas disponibles para hoy.",
                message_thread_id=thread_id_destino,
            )

        cleanup_tmp(epub_buffer)

    finally:
        # Eliminar mensaje de preparación
        if prep:
            try:
                await bot.delete_message(chat_id=destino, message_id=prep.message_id)
            except Exception as e:
                logger.debug(
                    "Could not delete prep message %s: %s",
                    getattr(prep, "message_id", None),
                    e,
                )

    # Mostrar opciones finales
    keyboard = [
        [
            InlineKeyboardButton(
                "📚 Volver a categorías", callback_data="volver_colecciones"
            )
        ],
        [
            InlineKeyboardButton(
                "↩️ Volver a la página anterior", callback_data="volver_ultima"
            )
        ],
        [InlineKeyboardButton("❌ Cerrar", callback_data="cerrar")],
    ]
    await bot.send_message(
        chat_id=chat_origen,
        text="Selecciona una opción:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        message_thread_id=thread_id_origen,
    )


async def enviar_libro_directo(
    bot,
    user_id: int,
    title: str,
    download_url: str,
    cover_url: str = None,
    target_chat_id: int = None,
    format_type: str = "standard",
):
    """
    Descarga y envía un libro directamente al usuario (para la Mini App).
    Replica el formato del bot: Portada -> Sinopsis -> Archivo.

    format_type: "standard", "fb_preview", "fb_direct"
    """
    try:
        # 1. Verificar límite
        if not can_download(user_id):
            await bot.send_message(
                chat_id=user_id, text="🚫 Has alcanzado tu límite de descargas por hoy."
            )
            return False

        # 2. Mensaje de preparación (siempre al usuario que interactúa)
        prep_msg = await bot.send_message(
            chat_id=user_id, text=f"⏳ Procesando: {title}..."
        )

        # Destino final del libro
        destino = target_chat_id if target_chat_id else user_id

        # 3. Descargar EPUB
        logger.info(f"Descargando EPUB desde: {download_url}")
        epub_bytes = await fetch_bytes(download_url, timeout=120)
        if not epub_bytes:
            error_msg = "❌ Error al descargar el archivo desde la fuente. Posible problema con Cloudflare o servidor de origen."
            logger.error(f"EPUB download failed for: {download_url}")
            await bot.send_message(
                chat_id=user_id,
                text=error_msg,
            )
            return False
        
        logger.info(f"EPUB descargado exitosamente: {len(epub_bytes) if isinstance(epub_bytes, bytes) else 'archivo temp'} bytes")

        # 4. Parsear metadatos del EPUB
        meta = {
            "titulo": title,
            "epub_version": "2.0",
            "fecha_modificacion": "Desconocida",
        }
        # Use centralized metadata enrichment
        from services.epub_service import enrich_metadata_from_epub

        logger.debug(f"Iniciando extracción de metadatos para: {title}")
        meta = await enrich_metadata_from_epub(epub_bytes, download_url, meta)
        logger.debug(f"Metadatos extraídos - titulo_serie: {meta.get('titulo_serie')}, internal_title: {meta.get('internal_title')}, autor: {meta.get('autor')}")

        # 5. Preparar Portada
        cover_bytes = extract_cover_from_epub(epub_bytes)
        portada_data = (
            cover_bytes
            if cover_bytes
            else (await fetch_bytes(cover_url) if cover_url else None)
        )

        # --- LOGICA FACEBOOK ---
        if format_type in ["fb_preview", "fb_direct"]:
            # Generar caption FB
            # Construir link público acortado
            from utils.url_cache import create_short_url
            from utils.helpers import formatear_titulo_fb, formatear_metadata_fb

            dl_domain = config.DL_DOMAIN.rstrip("/")
            if not dl_domain.startswith("http"):
                dl_domain = f"https://{dl_domain}"

            try:
                url_hash = create_short_url(download_url, book_title=title)
                public_link = f"{dl_domain}/api/dl/{url_hash}"
            except Exception as e:
                logger.error("Error creating short URL: %s", e)
                public_link = download_url  # Fallback

            # 1. Título
            title_block = formatear_titulo_fb(meta)

            # 2. Link de descarga
            link_block = f"⬇️ Descarga: {public_link}"

            # 3. Info del archivo (Actualizado, Tamaño)
            if isinstance(epub_bytes, (bytes, bytearray)):
                size_mb = len(epub_bytes) / (1024 * 1024)
            elif isinstance(epub_bytes, str) and os.path.exists(epub_bytes):
                size_mb = os.path.getsize(epub_bytes) / (1024 * 1024)
            else:
                size_mb = 0.0

            fecha_mod = meta.get("fecha_modificacion", "Desconocida")

            epub_info_block = (
                f"📅 Actualizado: {fecha_mod}\n" f"📦 Tamaño: {size_mb:.2f} MB"
            )

            # 4. Metadatos
            metadata_block = formatear_metadata_fb(meta)

            # 5. Sinopsis
            sinopsis = meta.get("sinopsis")
            sinopsis_block = ""
            if sinopsis:
                sinopsis_esc = escapar_html(sinopsis)
                sinopsis_block = f"<b>Sinopsis:</b>\n{sinopsis_esc}"

            # Construir caption final
            # IMPORTANTE: NO incluir "Vista Previa Facebook" aquí, se añade al enviar el mensaje
            parts = [
                title_block,
                link_block,
                epub_info_block,
                metadata_block,
                sinopsis_block,
            ]

            fb_caption = "\n\n".join(p for p in parts if p).strip()
            logger.debug(f"Caption FB generado, longitud: {len(fb_caption)}")

            if format_type == "fb_preview":
                # Enviar Portada y Caption al usuario
                if portada_data:
                    # Enviar portada sola primero? O con caption?
                    # User request: "mensaje que se enviara al char priavdo sera la vista previa facebbok (inluyendo la portada antes del mensaje principal)"
                    # Esto suena a: Foto con caption, o Foto y luego Texto.
                    # El bot actual suele enviar Foto con caption corto, y luego Texto largo.
                    # Pero para FB preview, mejor todo en uno si cabe, o separado.
                    # Telegram caption limit is 1024 chars. FB posts can be longer.
                    # Vamos a intentar enviar Foto sin caption (o titulo) y luego el texto completo.
                    await send_photo_bytes(
                        bot, user_id, None, portada_data, filename="cover.jpg"
                    )

                await bot.send_message(
                    chat_id=user_id,
                    text=fb_caption,
                    parse_mode="HTML",
                    disable_web_page_preview=False,
                )

            elif format_type == "fb_direct":
                # Publicar en FB
                from utils.helpers import validate_facebook_credentials

                is_valid, error_msg = validate_facebook_credentials(config)

                if not is_valid:
                    await bot.send_message(
                        chat_id=user_id, text=error_msg, parse_mode="HTML"
                    )
                    return False

                import httpx

                # Necesitamos una URL pública para la imagen si usamos 'url' param en FB API.
                # O subir como multipart/form-data.
                # La API actual usa 'url' param.
                # Si tenemos cover_url y es http, usamos esa.
                # Si no, tendríamos que subir bytes. La implementación actual de /api/facebook/publish usa 'url'.
                # Vamos a intentar usar cover_url si existe.

                fb_cover_url = cover_url
                if not fb_cover_url and portada_data:
                    # Si tenemos bytes pero no URL pública, es un problema para la API simple de 'url'.
                    # Podríamos subir bytes a FB, pero requiere cambiar la lógica de publicación.
                    # Por ahora, si no hay URL pública, avisamos.
                    # OJO: extract_cover_from_epub devuelve bytes.
                    pass

                if not fb_cover_url or not fb_cover_url.startswith("http"):
                    # Fallback: intentar usar la URL de la portada del feed si existe en meta
                    fb_cover_url = meta.get("portada")

                if not fb_cover_url or not fb_cover_url.startswith("http"):
                    await bot.send_message(
                        chat_id=user_id,
                        text="⚠️ No se pudo obtener una URL pública para la portada. Facebook requiere una URL pública.",
                    )
                    return False

                url = f"https://graph.facebook.com/{config.FACEBOOK_GROUP_ID}/photos"
                params = {
                    "url": fb_cover_url,
                    "caption": fb_caption.replace("<b>", "").replace(
                        "</b>", ""
                    ),  # Strip HTML
                    "access_token": config.FACEBOOK_PAGE_ACCESS_TOKEN,
                }

                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, params=params, timeout=30)
                    if resp.status_code != 200:
                        logger.error(f"FB Error: {resp.text}")
                        await bot.send_message(
                            chat_id=user_id,
                            text=f"❌ Error publicando en Facebook: {resp.text}",
                        )
                        return False

                await bot.send_message(
                    chat_id=user_id,
                    text="✅ Publicado exitosamente en el Grupo de Facebook.",
                )

        # --- LOGICA ESTANDAR ---
        else:
            # 5. Enviar Portada (Standard)
            if portada_data:
                mensaje_portada = formatear_mensaje_portada(meta)
                await send_photo_bytes(
                    bot,
                    destino,
                    mensaje_portada,
                    portada_data,
                    filename="cover.jpg",
                    parse_mode="HTML",
                )

            # 6. Enviar Sinopsis
            sinopsis = meta.get("sinopsis")
            if sinopsis:
                sinopsis_esc = escapar_html(sinopsis)
                texto = f"<b>Sinopsis:</b>\n<blockquote>{sinopsis_esc}</blockquote>\n#{generar_slug_from_meta(meta)}"
                await bot.send_message(chat_id=destino, text=texto, parse_mode="HTML")

            # 7. Enviar Archivo EPUB
            # Calcular tamaño
            if isinstance(epub_bytes, (bytes, bytearray)):
                size_mb = len(epub_bytes) / (1024 * 1024)
            elif isinstance(epub_bytes, str) and os.path.exists(epub_bytes):
                size_mb = os.path.getsize(epub_bytes) / (1024 * 1024)
            else:
                size_mb = 0.0
            version = meta.get("epub_version", "2.0")
            fecha = meta.get("fecha_modificacion", "Desconocida")
            titulo_vol = meta.get("titulo_volumen") or meta.get("titulo") or title

            caption = (
                f"📂 <b>{titulo_vol}</b>\n"
                f"ℹ️ Versión Epub: {version}\n"
                f"📅 Actualizado: {fecha}\n"
                f"📦 Tamaño: {size_mb:.2f} MB"
            )

            slug = generar_slug_from_meta(meta)
            if slug:
                caption += f"\n#{slug}"

            # Nombre de archivo desde URL
            fname = (
                unquote(urlparse(download_url).path.split("/")[-1]) or "archivo.epub"
            )

            sent_doc = await send_doc_bytes(
                bot, destino, caption, epub_bytes, filename=fname, parse_mode="HTML"
            )

            # Registrar en historial
            if sent_doc:
                from services.history_service import log_published_book
                file_info = {
                    "file_size": sent_doc.document.file_size,
                    "file_unique_id": sent_doc.document.file_unique_id
                }
                try:
                    log_published_book(
                        meta=meta,
                        message_id=sent_doc.message_id,
                        channel_id=sent_doc.chat.id,
                        file_info=file_info
                    )
                except Exception as e:
                    logger.error(f"Failed to log book history in enviar_libro_directo: {e}")

            # 8. Registrar descarga y notificar
            record_download(user_id)
            restantes = downloads_left(user_id)
            if restantes != "ilimitadas":
                await bot.send_message(
                    chat_id=user_id,
                    text=f"📥 Te quedan {restantes} descargas disponibles para hoy.",
                )

        # Limpieza
        try:
            await bot.delete_message(chat_id=user_id, message_id=prep_msg.message_id)
        except Exception as e:
            logger.debug(
                "Could not delete prep_msg %s: %s",
                getattr(prep_msg, "message_id", None),
                e,
            )

        return True

    except Exception as e:
        logger.error(f"Error en enviar_libro_directo: {e}", exc_info=True)
        await bot.send_message(
            chat_id=user_id, text=f"❌ Ocurrió un error interno: {str(e)}"
        )
        return False


async def preparar_post_facebook(update, context: ContextTypes.DEFAULT_TYPE, uid: int):
    """Genera vista previa del post de Facebook."""
    bot = context.bot
    user_state = state_manager.get_user_state(uid)

    # Recuperar datos del estado
    meta = user_state.get("meta_pendiente", {})
    epub_url = user_state.get("epub_url", "")
    titulo = user_state.get("titulo_pendiente", "")

    if not epub_url:
        await bot.send_message(chat_id=uid, text="❌ No hay libro seleccionado.")
        return

    # Construir link público acortado con SHA256 persistente
    from utils.url_cache import create_short_url
    from utils.helpers import formatear_titulo_fb, formatear_metadata_fb, escapar_html

    dl_domain = config.DL_DOMAIN.rstrip("/")
    if not dl_domain.startswith("http"):
        dl_domain = f"https://{dl_domain}"

    # Crear hash y guardar en BD (persistente) con metadata del libro
    try:
        url_hash = create_short_url(epub_url, book_title=titulo)
    except Exception as e:
        logger.error("Error creando short URL: %s", e)
        await bot.send_message(
            chat_id=uid,
            text="❌ No fue posible generar el enlace acortado. Intenta de nuevo más tarde.",
        )
        return
    public_link = f"{dl_domain}/api/dl/{url_hash}"

    # 1. Título
    title_block = formatear_titulo_fb(meta)

    # 2. Link de descarga
    link_block = f"⬇️ Descarga: {public_link}"

    # 3. Info del archivo (Actualizado, Tamaño) - Versión removida según solicitud
    epub_buffer = user_state.get("epub_buffer")
    if epub_buffer:
        if isinstance(epub_buffer, (bytes, bytearray)):
            size_mb = len(epub_buffer) / (1024 * 1024)
        elif isinstance(epub_buffer, str) and os.path.exists(epub_buffer):
            size_mb = os.path.getsize(epub_buffer) / (1024 * 1024)
        else:
            size_mb = 0.0
    else:
        size_mb = 0.0

    fecha_mod = meta.get("fecha_modificacion", "Desconocida")

    epub_info_block = f"📅 Actualizado: {fecha_mod}\n" f"📦 Tamaño: {size_mb:.2f} MB"

    # 4. Metadatos (Maquetado, Categoría, etc.)
    metadata_block = formatear_metadata_fb(meta)

    # 5. Sinopsis
    sinopsis = meta.get("sinopsis")
    # Intentar obtener sinopsis desde OPDS si no existe en meta
    if not sinopsis:
        series_id = user_state.get("series_id")
        volume_id = user_state.get("volume_id")
        if volume_id and series_id:
            try:
                sinopsis = await obtener_sinopsis_opds_volumen(series_id, volume_id)
            except Exception:
                sinopsis = None
        if not sinopsis and series_id:
            try:
                sinopsis = await obtener_sinopsis_opds(series_id)
            except Exception:
                sinopsis = None

    sinopsis_block = ""
    if sinopsis:
        sinopsis_esc = escapar_html(sinopsis)
        sinopsis_block = f"<b>Sinopsis:</b>\n{sinopsis_esc}"

    # Construir caption final
    # Orden: Título -> Link -> Info -> Metadata -> Sinopsis
    parts = [
        "<b>Vista Previa Facebook:</b>",
        title_block,
        link_block,
        epub_info_block,
        metadata_block,
        sinopsis_block,
    ]

    # Unir partes con doble salto de línea, filtrando vacíos
    caption = "\n\n".join(p for p in parts if p).strip()

    # Guardar en estado para publicación
    user_state["fb_caption"] = caption

    # Enviar vista previa (caption)
    btns = []
    btns.append(
        [InlineKeyboardButton("🚀 Publicar ahora", callback_data="publicar_fb")]
    )

    btns.append(
        [
            InlineKeyboardButton("🗑️ Descartar", callback_data="descartar_fb"),
            InlineKeyboardButton("↩️ Volver", callback_data="volver_ultima"),
        ]
    )

    logger.debug(
        "preparar_post_facebook: uid=%s preview_chat=%s thread=%s meta_title=%r",
        uid,
        user_state.get("publish_command_origin"),
        user_state.get("publish_command_thread_id"),
        titulo,
    )

    # Enviar como mensaje nuevo — preferir el chat donde se ejecutó el comando
    preview_chat = user_state.get("publish_command_origin") or uid
    preview_thread = user_state.get("publish_command_thread_id")
    await bot.send_message(
        chat_id=preview_chat,
        text=f"📝 <b>Vista Previa Facebook:</b>\n\n{caption}",
        parse_mode="HTML",
        disable_web_page_preview=False,
        reply_markup=InlineKeyboardMarkup(btns),
        message_thread_id=preview_thread,
    )


async def _publish_choice_facebook(
    update, context: ContextTypes.DEFAULT_TYPE, uid: int
):
    """Flow when a publisher chooses to publish on Facebook: send cover alone then prepare preview."""
    bot = context.bot
    st = state_manager.get_user_state(uid)

    # Clear awaiting flag (we're handling the choice now)
    st.pop("awaiting_publish_target", None)

    logger.debug(
        "_publish_choice_facebook: handling for uid=%s pending=%s",
        uid,
        st.get("pending_pub_book"),
    )

    # Borrar mensaje "Preparando..." si existe
    menu_prep = st.pop("pending_pub_menu_prep", None)
    if menu_prep:
        try:
            await bot.delete_message(chat_id=menu_prep[0], message_id=menu_prep[1])
        except Exception as e:
            logger.debug("No se pudo borrar mensaje 'Preparando...' (FB): %s", e)

    # If we have a pending_pub_book (set at selection), use it; otherwise rely on meta_pendiente
    pending = st.pop("pending_pub_book", None)
    epub_url = st.get("epub_url", "")
    epub_buffer = st.get("epub_buffer")
    meta = st.get("meta_pendiente", {})
    if pending:
        # populate ephemeral state for this publish flow
        st["titulo_pendiente"] = pending.get("titulo")
        st["portada_pendiente"] = pending.get("portada")
        epub_url = pending.get("href")
        st["epub_url"] = epub_url

    # Try to obtain cover bytes from buffer or fetch cover_url from meta
    cover_bytes = None
    try:
        if epub_buffer:
            from services.epub_service import extract_cover_from_epub

            cover_bytes = extract_cover_from_epub(epub_buffer)
    except Exception:
        cover_bytes = None

    # If cover not extracted from buffer, try the pending portada or meta portada
    portada_url = pending.get("portada") if pending else meta.get("portada")
    if not cover_bytes and portada_url:
        cover_bytes = await fetch_bytes(portada_url)

    # If we still don't have metadata or buffer, try to fetch EPUB to build meta/cover
    if (not cover_bytes or not meta) and epub_url:
        epub_downloaded = await fetch_bytes(epub_url, timeout=60)
        if epub_downloaded:
            st["epub_buffer"] = epub_downloaded
            epub_buffer = epub_downloaded
            # Use centralized metadata enrichment
            from services.epub_service import enrich_metadata_from_epub

            meta = await enrich_metadata_from_epub(epub_downloaded, epub_url, meta)
            st["meta_pendiente"] = meta

            if not cover_bytes:
                try:
                    cover_bytes = extract_cover_from_epub(epub_downloaded)
                except Exception:
                    cover_bytes = None

    logger.debug(
        "_publish_choice_facebook: sending cover to origin=%s (thread=%s), have_cover=%s",
        st.get("publish_command_origin"),
        st.get("publish_command_thread_id"),
        bool(cover_bytes),
    )

    # Send only cover (no caption) if available
    if cover_bytes:
        # send the cover to the chat where the publisher invoked the command, default to uid
        dest_chat = st.get("publish_command_origin") or uid
        thread = st.get("publish_command_thread_id")
        await send_photo_bytes(
            bot,
            dest_chat,
            caption=None,
            data_or_path=cover_bytes,
            filename="cover.jpg",
            parse_mode=None,
            message_thread_id=thread,
        )
        # If cover was a temp file path, cleanup
        if isinstance(cover_bytes, str):
            cleanup_tmp(cover_bytes)

    # Now prepare and send the FB preview text to the publisher (private chat)
    await preparar_post_facebook(update, context, uid)

    # cleanup pending menu_prep
    st.pop("pending_pub_menu_prep", None)
    st.pop("publish_command_origin", None)
    st.pop("publish_command_thread_id", None)


async def _publish_choice_telegram(
    update, context: ContextTypes.DEFAULT_TYPE, uid: int
):
    """Continue publish flow for Telegram: send portada, sinopsis, info and buttons (omit FB post option)."""
    bot = context.bot
    st = state_manager.get_user_state(uid)
    st.pop("awaiting_publish_target", None)
    logger.debug(
        "_publish_choice_telegram: uid=%s pending=%s destino=%s chat_origen=%s",
        uid,
        st.get("pending_pub_book"),
        st.get("destino"),
        st.get("chat_origen"),
    )

    destino = st.get("destino") or update.effective_chat.id
    chat_origen = st.get("chat_origen") or destino
    thread_id_origen = st.get("message_thread_id")

    meta = st.get("meta_pendiente", {})
    epub_buffer = st.get("epub_buffer")
    portada_url = st.get("portada_pendiente") or meta.get("portada")

    # Prepare caption for portada
    mensaje_portada = formatear_mensaje_portada(meta)

    # Extract cover from buffer if present
    cover_bytes = None
    if epub_buffer:
        try:
            cover_bytes = extract_cover_from_epub(epub_buffer)
        except Exception:
            cover_bytes = None

    portada_data = (
        cover_bytes
        if cover_bytes
        else (await fetch_bytes(portada_url, timeout=15) if portada_url else None)
    )

    await send_photo_bytes(
        bot,
        destino,
        mensaje_portada,
        portada_data,
        filename="cover.jpg",
        parse_mode="HTML",
        message_thread_id=thread_id_origen,
    )
    if not cover_bytes and isinstance(portada_data, str):
        cleanup_tmp(portada_data)

    # Sinopsis
    sinopsis = meta.get("sinopsis")
    if not sinopsis:
        series_id = st.get("series_id")
        volume_id = st.get("volume_id")
        if series_id and volume_id:
            sinopsis = await obtener_sinopsis_opds_volumen(series_id, volume_id)
        if not sinopsis and series_id:
            try:
                sinopsis = await obtener_sinopsis_opds(series_id)
            except Exception as e:
                logger.debug(
                    "Error fetching sinopsis in publish_choice_telegram: %s", e
                )

    if sinopsis:
        sinopsis_esc = escapar_html(sinopsis)
        texto = f"<b>Sinopsis:</b>\n<blockquote>{sinopsis_esc}</blockquote>\n#{generar_slug_from_meta(meta)}"
        try:
            await bot.send_message(
                chat_id=destino,
                text=texto,
                parse_mode="HTML",
                message_thread_id=thread_id_origen,
            )
        except BadRequest as e:
            if "Message thread not found" in str(e) and thread_id_origen is not None:
                await bot.send_message(
                    chat_id=destino,
                    text=texto,
                    parse_mode="HTML",
                    message_thread_id=None,
                )
            else:
                raise e
    else:
        slug = generar_slug_from_meta(meta)
        fallback = (
            f"Sinopsis: (no disponible)\n#{slug}"
            if slug
            else "Sinopsis: (no disponible)"
        )
        try:
            await bot.send_message(
                chat_id=destino, text=fallback, message_thread_id=thread_id_origen
            )
        except BadRequest as e:
            if "Message thread not found" in str(e) and thread_id_origen is not None:
                await bot.send_message(
                    chat_id=destino, text=fallback, message_thread_id=None
                )
            else:
                raise e

    # Info adicional si tenemos EPUB
    if epub_buffer:
        if isinstance(epub_buffer, (bytes, bytearray)):
            size_mb = len(epub_buffer) / (1024 * 1024)
        elif isinstance(epub_buffer, str) and os.path.exists(epub_buffer):
            size_mb = os.path.getsize(epub_buffer) / (1024 * 1024)
        else:
            size_mb = 0.0

        version = meta.get("epub_version", "2.0")
        fecha = meta.get("fecha_modificacion", "Desconocida")
        titulo_vol = meta.get("titulo_volumen") or st.get(
            "titulo_pendiente", "Desconocido"
        )

        info_text = (
            f"📂 <b>{titulo_vol}</b>\n"
            f"ℹ️ Versión Epub: {version}\n"
            f"📅 Actualizado: {fecha}\n"
            f"📦 Tamaño: {size_mb:.2f} MB"
        )
        try:
            msg_info = await bot.send_message(
                chat_id=chat_origen,
                text=info_text,
                parse_mode="HTML",
                message_thread_id=thread_id_origen,
            )
        except BadRequest as e:
            if "Message thread not found" in str(e) and thread_id_origen is not None:
                msg_info = await bot.send_message(
                    chat_id=chat_origen,
                    text=info_text,
                    parse_mode="HTML",
                    message_thread_id=None,
                )
            else:
                raise e
        st["msg_info_id"] = msg_info.message_id

    # Botones: solo descarga y volver (omitimos Post FB porque eligió Telegram)
    keyboard = [
        [InlineKeyboardButton("📥 Descargar EPUB", callback_data="descargar_epub")],
        [InlineKeyboardButton("↩️ Volver", callback_data="volver_ultima")],
    ]

    try:
        sent = await bot.send_message(
            chat_id=chat_origen,
            text="¿Deseas descargar este EPUB?",
            parse_mode="HTML",
            message_thread_id=thread_id_origen,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except BadRequest as e:
        if "Message thread not found" in str(e) and thread_id_origen is not None:
            sent = await bot.send_message(
                chat_id=chat_origen,
                text="¿Deseas descargar este EPUB?",
                parse_mode="HTML",
                message_thread_id=None,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            raise e
    st["msg_botones_id"] = sent.message_id


async def publicar_facebook_action(
    update, context: ContextTypes.DEFAULT_TYPE, uid: int
):
    """Publica el post en Facebook."""
    bot = context.bot
    user_state = state_manager.get_user_state(uid)

    # Validar credenciales antes de proceder
    from utils.helpers import validate_facebook_credentials

    is_valid, error_msg = validate_facebook_credentials(config)

    if not is_valid:
        await bot.send_message(chat_id=uid, text=error_msg, parse_mode="HTML")
        return

    caption = user_state.get("fb_caption")

    if not caption:
        await bot.send_message(chat_id=uid, text="❌ No hay post preparado.")
        return

    # Intentar obtener portada
    epub_buffer = user_state.get("epub_buffer")
    cover_bytes = None
    if epub_buffer:
        cover_bytes = extract_cover_from_epub(epub_buffer)

    if not cover_bytes:
        await bot.send_message(
            chat_id=uid, text="⚠️ No se pudo obtener la portada para subir a Facebook."
        )
        return

    # Subir a Facebook usando Graph API
    import httpx

    logger.debug(
        "publicar_facebook_action: uid=%s publish_command_origin=%s thread=%s caption_len=%s",
        uid,
        user_state.get("publish_command_origin"),
        user_state.get("publish_command_thread_id"),
        len(caption) if caption else 0,
    )

    # Send progress message in the chat where the preview/button was clicked (origin) if available
    publish_chat = (
        user_state.get("publish_command_origin") or update.effective_chat.id or uid
    )
    publish_thread = user_state.get("publish_command_thread_id")
    try:
        msg = await bot.send_message(
            chat_id=publish_chat,
            text="⏳ Publicando en Facebook...",
            message_thread_id=publish_thread,
        )
    except BadRequest as e:
        if "Message thread not found" in str(e) and publish_thread is not None:
            msg = await bot.send_message(
                chat_id=publish_chat,
                text="⏳ Publicando en Facebook...",
                message_thread_id=None,
            )
        else:
            raise e

    try:
        url = f"https://graph.facebook.com/{config.FACEBOOK_GROUP_ID}/photos"

        # Limpiar caption de HTML para FB
        clean_caption = (
            caption.replace("<b>", "")
            .replace("</b>", "")
            .replace("<i>", "")
            .replace("</i>", "")
        )

        data = {
            "caption": clean_caption,
            "access_token": config.FACEBOOK_PAGE_ACCESS_TOKEN,
            "published": "true",
        }

        # Enviar archivo
        files = {"source": ("cover.jpg", io.BytesIO(cover_bytes), "image/jpeg")}

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=data, files=files, timeout=60)
            resp.raise_for_status()
            fb_res = resp.json()

        # Notify origin chat and private publisher chat (if different)
        await bot.edit_message_text(
            chat_id=publish_chat,
            message_id=msg.message_id,
            text=f"✅ Publicado exitosamente!\nID: {fb_res.get('id')}",
        )

    except Exception as e:
        logger.error(f"Error publicando en FB: {e}")
        await bot.edit_message_text(
            chat_id=publish_chat,
            message_id=msg.message_id,
            text=f"❌ Error al publicar: {str(e)}",
        )
