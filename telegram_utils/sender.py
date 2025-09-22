import os
import io
import logging
from telegram import InputFile

from http.fetcher import cleanup_tmp


async def send_photo_bytes(bot, chat_id, caption, data_or_path, filename="photo.jpg"):
    """
    data_or_path: bytes o path a file. Returns telegram.Message or None.
    """
    if not data_or_path:
        return None
    try:
        if isinstance(data_or_path, (bytes, bytearray)):
            bio = io.BytesIO(data_or_path)
            bio.name = filename
            bio.seek(0)
            input_file = InputFile(bio, filename=filename)
            return await bot.send_photo(chat_id=chat_id, photo=input_file, caption=caption)

        elif isinstance(data_or_path, str) and os.path.exists(data_or_path):
            f = open(data_or_path, "rb")
            try:
                input_file = InputFile(f, filename=filename)
                res = await bot.send_photo(chat_id=chat_id, photo=input_file, caption=caption)
            finally:
                try:
                    f.close()
                except Exception:
                    pass
            return res
        else:
            return None
    except Exception as e:
        logging.debug("Error send_photo_bytes: %s", e)
        return None
    finally:
        cleanup_tmp(data_or_path)


async def send_doc_bytes(bot, chat_id, caption, data_or_path, filename="file.epub"):
    """
    data_or_path: bytes o ruta a fichero. Devuelve telegram.Message o None.
    """
    if not data_or_path:
        return None
    try:
        if isinstance(data_or_path, (bytes, bytearray)):
            bio = io.BytesIO(data_or_path)
            bio.name = filename
            bio.seek(0)
            input_file = InputFile(bio, filename=filename)
            return await bot.send_document(chat_id=chat_id, document=input_file, caption=caption)

        elif isinstance(data_or_path, str) and os.path.exists(data_or_path):
            f = open(data_or_path, "rb")
            try:
                input_file = InputFile(f, filename=filename)
                res = await bot.send_document(chat_id=chat_id, document=input_file, caption=caption)
            finally:
                try:
                    f.close()
                except Exception:
                    pass
            return res

        else:
            return None
    except Exception as e:
        logging.debug("Error send_doc_bytes: %s", e)
        return None
    finally:
        cleanup_tmp(data_or_path)