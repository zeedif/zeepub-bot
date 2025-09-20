import re
import os
import hashlib
import datetime
import logging
import xml.etree.ElementTree as ET
import io
import asyncio
import tempfile
import zipfile
from typing import Optional, Dict, Any

import feedparser
import aiohttp
from dotenv import load_dotenv
from urllib.parse import urljoin, urlparse, unquote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
import html  # para escapar texto en HTML parse_mode

# ===== CONFIGURACIÓN =====
load_dotenv()
logging.basicConfig(level=logging.DEBUG)

BASE_URL = os.getenv("BASE_URL")
OPDS_ROOT_START_SUFFIX = os.getenv("OPDS_ROOT_START")
OPDS_ROOT_EVIL_SUFFIX = os.getenv("OPDS_ROOT_EVIL")
KAVITA_API_KEY = os.getenv("KAVITA_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SECRET_SEED = os.getenv("SECRET_SEED")

# Validar variables críticas
missing = []
if not TELEGRAM_TOKEN:
    missing.append("TELEGRAM_TOKEN")
if not BASE_URL:
    missing.append("BASE_URL")
if not OPDS_ROOT_START_SUFFIX:
    missing.append("OPDS_ROOT_START")
if not OPDS_ROOT_EVIL_SUFFIX:
    missing.append("OPDS_ROOT_EVIL")
if missing:
    raise SystemExit(f"Faltan variables de entorno: {', '.join(missing)}")

OPDS_ROOT_START = f"{BASE_URL}{OPDS_ROOT_START_SUFFIX}"
OPDS_ROOT_EVIL = f"{BASE_URL}{OPDS_ROOT_EVIL_SUFFIX}"

user_state = {}

# -----------------------
# Global aiohttp session and limits
# -----------------------
_GLOBAL_AIOSESSION = None
MAX_IN_MEMORY_BYTES = 10 * 1024 * 1024  # 10 MB threshold; ajustar si hace falta
DEFAULT_AIOHTTP_TIMEOUT = 60  # segundos por defecto para la sesión global

def _cleanup_tmp(path: str):
    "Borra un fichero temporal si path es ruta existente."
    if isinstance(path, str) and os.path.exists(path):
        try:
            os.unlink(path)
        except Exception:
            pass

def mostrar_feed(url):
    """Parsea un feed OPDS y devuelve el objeto feedparser, o None si hay error."""
    feed = feedparser.parse(url)
    return None if feed.bozo else feed

def _get_global_session():
    global _GLOBAL_AIOSESSION
    if _GLOBAL_AIOSESSION is None:
        connector = aiohttp.TCPConnector(limit=20)
        _GLOBAL_AIOSESSION = aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=DEFAULT_AIOHTTP_TIMEOUT))
    return _GLOBAL_AIOSESSION

# -----------------------
# Helpers
# -----------------------
def ensure_user(uid: int):
    if uid not in user_state:
        user_state[uid] = {
            "historial": [],
            "libros": {},
            "colecciones": {},
            "nav": {"prev": None, "next": None},
            "titulo": "📚 Todas las bibliotecas",
            "destino": None,
            "chat_origen": None,
            "esperando_destino_manual": False,
            "esperando_busqueda": False,
            "esperando_password": False,
            "ultima_pagina": None,
            "opds_root": OPDS_ROOT_START,
            "opds_root_base": OPDS_ROOT_START
        }
    return user_state[uid]

def get_six_hour_password():
    now = datetime.datetime.now()
    bloque = now.hour // 6
    raw = f"{SECRET_SEED}{now.year}-{now.month}-{now.day}-B{bloque}"
    return hashlib.sha256(raw.encode()).hexdigest()[:8]

def abs_url(base, href):
    return href if href.startswith("http") else urljoin(base, href)

def norm_string(s: str) -> str:
    """Normaliza una cadena: colapsa espacios y pasa a lowercase (útil para comparaciones)."""
    return " ".join((s or "").split()).casefold()

def limpiar_html_basico(texto_html: str) -> str:
    """
    Convierte <br/> en saltos de línea, elimina otras etiquetas HTML básicas,
    y limpia líneas vacías redundantes.
    """
    if not texto_html:
        return ""
    texto_html = texto_html.replace("<br/>", "\n").replace("<br>", "\n")
    texto_limpio = re.sub(r"<.*?>", "", texto_html)
    return "\n".join([ln.rstrip() for ln in texto_limpio.strip().splitlines() if ln.strip()])

def build_search_url(query: str, uid: int | None = None) -> str:
    """
    Reconstruye la URL de búsqueda usando el OPDS root actual del usuario (si existe).
    """
    root = OPDS_ROOT_START
    if uid and uid in user_state:
        root = user_state[uid].get("opds_root", OPDS_ROOT_START)

    if "/series" in root:
        root_series = root.split("?")[0]
    else:
        root_series = f"{root}/series"
    return f"{root_series}?query={query}"

def find_zeepubs_destino(feed, prefer_libraries: bool = False):
    """
    Dado un feedparser.FeedParserDict, intenta localizar la subsección de ZeePubs.
    - Si prefer_libraries=True prioriza enlaces con /libraries o /collections (para abrir biblioteca).
    - Si prefer_libraries=False usa heurística conservadora: buscar 'zeepub(s)' en título o
      devolver único candidato subsección si solo existe uno (evita entrar automáticamente en feeds con muchas subsecciones).
    Devuelve href absoluto o None.
    """
    if not feed:
        logging.debug("find_zeepubs_destino: feed is None")
        return None

    entries = getattr(feed, "entries", [])
    logging.debug("find_zeepubs_destino: feed title=%s entries=%d", getattr(feed, "feed", {}).get("title", None), len(entries))

    def norm(s): return " ".join((s or "").split()).casefold()

    candidatos = []  # (title, href)
    for entry in entries:
        title = getattr(entry, "title", "")
        logging.debug("find_zeepubs_destino: entry.title=%r", title)
        tnorm = norm(title)
        for link in getattr(entry, "links", []):
            rel = getattr(link, "rel", "")
            href = getattr(link, "href", "")
            logging.debug(" find link rel=%r href=%r (entry=%r)", rel, href, title)
            if rel == "subsection" and href:
                full = abs_url(BASE_URL, href)
                candidatos.append((title, full))
                # coincidencia explícita 'zeepub' -> devolver inmediatamente
                if "zeepub" in tnorm or "zeepubs" in tnorm or tnorm == norm("ZeePubs [ES]"):
                    logging.debug("find_zeepubs_destino: título coincide con 'zeepub(s)': %r -> %s", title, full)
                    return full

    # Si el llamador pidió priorizar bibliotecas/hrefs típicos, comprobar esos patterns primero
    from urllib.parse import urlparse
    if prefer_libraries:
        for title, href in candidatos:
            path = urlparse(href).path.lower()
            if "/libraries" in path or "/collections" in path or "/library" in path:
                logging.debug("find_zeepubs_destino: (prefer_libraries) href contiene patrón de biblioteca, eligiendo %s (title=%r)", href, title)
                return href
        # fallback: si hay título que contenga 'biblioteca' también usarlo
        for title, href in candidatos:
            if "bibliotec" in norm(title):
                logging.debug("find_zeepubs_destino: (prefer_libraries) título sugiere 'biblioteca', eligiendo %s (title=%r)", href, title)
                return href

    # Comportamiento conservador por defecto (usado en /start y primera carga del root):
    # Si solo hay un candidato, devolverlo (compatibilidad con casos simples)
    if len(candidatos) == 1:
        logging.debug("find_zeepubs_destino: único candidato disponible, devolviendo %s", candidatos[0][1])
        return candidatos[0][1]

    logging.debug("find_zeepubs_destino: no se encontró destino (candidatos=%s)", [c for _, c in candidatos])
    return None

# -----------------------
# HTTP download helper (reusable session + streaming)
# -----------------------
async def fetch_bytes(url: str, session: aiohttp.ClientSession = None, timeout: int = 15):
    """
    Descarga y devuelve:
      - bytes cuando el contenido es pequeño <= MAX_IN_MEMORY_BYTES
      - ruta a fichero temporal (str) cuando es grande o conviene no mantener en RAM
    Devuelve None en fallo.
    """
    try:
        sess = session or _get_global_session()
        async with sess.get(url, timeout=timeout) as resp:
            resp.raise_for_status()
            cl = resp.headers.get("Content-Length")
            total = None
            if cl:
                try:
                    total = int(cl)
                except Exception:
                    total = None

            if total is not None and total > MAX_IN_MEMORY_BYTES:
                tmp = tempfile.NamedTemporaryFile(delete=False)
                try:
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        tmp.write(chunk)
                    tmp.close()
                    return tmp.name
                except Exception:
                    try:
                        os.unlink(tmp.name)
                    except Exception:
                        pass
                    return None
            else:
                data = await resp.read()
                if len(data) > MAX_IN_MEMORY_BYTES:
                    tmp = tempfile.NamedTemporaryFile(delete=False)
                    try:
                        tmp.write(data)
                        tmp.close()
                        return tmp.name
                    except Exception:
                        try:
                            os.unlink(tmp.name)
                        except Exception:
                            pass
                        return None
                return data
    except Exception as e:
        logging.debug("Error fetch_bytes %s: %s", url, e)
        return None

# -----------------------
# Feedparser + XML helpers
# -----------------------
async def parse_feed_from_url(url: str):
    """
    Descarga (usando fetch_bytes) y parsea un feed OPDS con feedparser.
    Maneja tanto bytes como rutas a ficheros temporales que devuelve fetch_bytes.
    Devuelve None en fallo.
    """
    data = await fetch_bytes(url, timeout=20)
    if not data:
        return None

    try:
        # Si fetch_bytes devolvió bytes en memoria, pasarlos directamente a feedparser
        if isinstance(data, (bytes, bytearray)):
            feed = await asyncio.to_thread(feedparser.parse, data)
        # Si devolvió una ruta a fichero, leer el contenido y parsear los bytes
        elif isinstance(data, str) and os.path.exists(data):
            try:
                with open(data, "rb") as f:
                    content = f.read()
            except Exception:
                return None
            feed = await asyncio.to_thread(feedparser.parse, content)
        else:
            # Fallback: pasar lo que sea (por ejemplo una URL string) a feedparser
            feed = await asyncio.to_thread(feedparser.parse, data)

        return None if getattr(feed, "bozo", False) else feed
    finally:
        # Limpieza segura del posible fichero temporal creado por fetch_bytes
        _cleanup_tmp(data)

# -----------------------
# EPUB / OPF parsing helpers
# -----------------------
def _parse_opf_bytes(data: bytes) -> Dict[str, Any]:
    """
    Parsea bytes de un .opf y extrae metadatos relevantes.
    Mejora:
      - maneja elementos con namespaces buscando por localname
      - identifica roles que refinen contributors (ej. <meta property="role" refines="#contrib2">mrk</meta>)
      - cuando faltan roles, aplica heurística sobre nombres de contributors para detectar maquetadores
    Devuelve dict con keys: titulo_volumen, titulo_serie, autores (list),
    ilustrador, generos (list), demografia (list), categoria, maquetadores (list),
    traductor (str), publisher (str), publisher_url (str).
    """
    try:
        root = ET.fromstring(data)
    except Exception:
        return {}

    def local_name(elem):
        tag = elem.tag
        if isinstance(tag, str) and "}" in tag:
            return tag.rsplit("}", 1)[1]
        return tag

    out: Dict[str, Any] = {
        "titulo_volumen": None,
        "titulo_serie": None,
        "autores": [],
        "ilustrador": None,
        "generos": [],
        "demografia": [],
        "categoria": None,
        "maquetadores": [],
        "traductor": None,
        "publisher": None,
        "publisher_url": None,
    }

    # title (buscar por localname 'title' en DC)
    for el in root.iter():
        if local_name(el).lower() == "title" and el.tag.endswith("}title") or local_name(el).lower() == "title":
            if el.text and not out["titulo_volumen"]:
                out["titulo_volumen"] = el.text.strip()
                break

    # belongs-to-collection meta (series) -> buscar meta con property=belongs-to-collection (ignorar namespace)
    for el in root.iter():
        if local_name(el).lower() == "meta":
            prop = el.attrib.get("property", "") or el.attrib.get("{http://www.idpf.org/2007/opf}property", "")
            if prop == "belongs-to-collection" and el.text:
                out["titulo_serie"] = el.text.strip()
                break

    # Recolectar creators/contributors (por localname)
    creators = []
    contributors = []
    id_to_name = {}
    for el in root.iter():
        ln = local_name(el).lower()
        if ln in ("creator", "dc:creator", "dc_creator", "creator"):
            text = (el.text or "").strip()
            if text:
                creators.append(text)
            cid = el.attrib.get("id")
            if cid and text:
                id_to_name[cid] = text
        elif ln in ("contributor", "dc:contributor", "dc_contributor", "contributor"):
            text = (el.text or "").strip()
            if text:
                contributors.append(text)
            cid = el.attrib.get("id")
            if cid and text:
                id_to_name[cid] = text

    out["autores"] = creators

    # subjects -> géneros y demografía (recoger todos los dc:subject)
    subjects = []
    for el in root.iter():
        if local_name(el).lower() in ("subject", "dc:subject"):
            txt = (el.text or "").strip()
            if txt:
                subjects.append(txt)
    # simple split into demografía vs generos by keywords
    dem_keywords = {"juvenil", "seinen", "shounen", "shoujo", "josei", "kodomomuke", "juvenile", "chicos", "chicos/shounen", "shônen", "shounen"}
    dem = []
    genres = []
    for s in subjects:
        sl = s.lower()
        if any(k in sl for k in dem_keywords):
            dem.append(s)
        else:
            genres.append(s)
    out["generos"] = genres
    out["demografia"] = dem

    # tipo (categoria) -> dc:type
    for el in root.iter():
        if local_name(el).lower() in ("type", "dc:type"):
            if el.text:
                out["categoria"] = el.text.strip()
                break

    # publisher
    for el in root.iter():
        if local_name(el).lower() in ("publisher", "dc:publisher", "dc_publisher"):
            if el.text:
                out["publisher"] = el.text.strip()
                break

    # identifier -> buscar URL/urn:uri
    for el in root.iter():
        if local_name(el).lower() in ("identifier", "dc:identifier", "dc_identifier"):
            txt = (el.text or "").strip()
            if txt and (txt.startswith("http") or txt.startswith("urn:uri:") or txt.startswith("https")):
                if txt.startswith("urn:uri:"):
                    parts = txt.split(":", 2)
                    if len(parts) == 3:
                        txt = parts[-1]
                out["publisher_url"] = txt
                break

    # Parse meta role elements (buscar por localname 'meta' y atributo property == 'role')
    roles = {}  # id -> rolecode
    for el in root.iter():
        if local_name(el).lower() == "meta":
            prop = el.attrib.get("property", "") or el.attrib.get("{http://www.idpf.org/2007/opf}property", "")
            if prop and prop.lower() == "role":
                ref = el.attrib.get("refines", "") or el.attrib.get("{http://www.idpf.org/2007/opf}refines", "")
                if ref and el.text:
                    rid = ref.lstrip('#')
                    roles[rid] = (el.text or "").strip().lower()

    # Map roles -> maquetadores/traductor/ilustrador using id_to_name
    maquetador_roles = {"mrk", "dst", "mqt", "mkr"}
    for rid, role in roles.items():
        name = id_to_name.get(rid)
        if not name:
            continue
        if role in maquetador_roles:
            if name not in out["maquetadores"]:
                out["maquetadores"].append(name)
        elif role in {"trl", "translator"}:
            out["traductor"] = name
        elif role in {"ill", "illustrator", "artist"}:
            out["ilustrador"] = name
        elif role in {"aut", "author"} and not out["autores"]:
            out["autores"].append(name)

    # Si no encontramos ilustrador vía roles, intentar heurística en contributors
    if not out["ilustrador"]:
        for name in contributors:
            low = name.lower()
            if any(tok in low for tok in ("ill", "illustrator", "artist", "ilustr")):
                out["ilustrador"] = name
                break
        if not out["ilustrador"] and len(out["autores"]) > 1:
            out["ilustrador"] = out["autores"][-1]

    # Heurística adicional para maquetadores:
    # 1) Si alguna contributor contiene palabras clave (zeepub, saosora, saosora) añadirla
    # 2) Si aún no hay maquetadores, y hay contributors id_to_name, añadir a todos los contributors
    heur_keywords = ("zeepub", "zeepubs", "saosora", "saosora", "saosor", "saosora")
    # add contributors that match keywords
    for name in (list(id_to_name.values()) + contributors):
        low = (name or "").lower()
        if any(k in low for k in heur_keywords):
            if name not in out["maquetadores"]:
                out["maquetadores"].append(name)
    # fallback: if still empty, try contributors that look like groups (contain ' ' or uppercase patterns)
    if not out["maquetadores"]:
        for name in contributors:
            if len(name) > 1 and name not in out["maquetadores"]:
                out["maquetadores"].append(name)
        # as a last resort, try id_to_name values
        if not out["maquetadores"]:
            for name in id_to_name.values():
                if name not in out["maquetadores"]:
                    out["maquetadores"].append(name)

    # dedupe maquetadores preserving order
    seen = set()
    maqs = []
    for m in out["maquetadores"]:
        if m not in seen:
            seen.add(m)
            maqs.append(m)
    out["maquetadores"] = maqs

    return out

async def parse_opf_from_epub(data_or_path) -> Optional[Dict[str, Any]]:
    """
    Extrae y parsea el content.opf de un EPUB (bytes o ruta a archivo).
    Devuelve dict (posible vacío) o None en fallo.
    """
    def _read_opf_from_zip(z: zipfile.ZipFile):
        try:
            cont = z.read('META-INF/container.xml')
            try:
                tree = ET.fromstring(cont)
            except Exception:
                tree = None
            opf_path = None
            if tree is not None:
                for el in tree.iter():
                    tag = el.tag.lower()
                    if tag.endswith('rootfile'):
                        opf_path = el.attrib.get('full-path')
                        if opf_path:
                            break
            if not opf_path:
                for name in z.namelist():
                    if name.lower().endswith('.opf'):
                        opf_path = name
                        break
            if not opf_path:
                return None
            data = z.read(opf_path)
            return data
        except KeyError:
            for name in z.namelist():
                if name.lower().endswith('.opf'):
                    return z.read(name)
            return None

    try:
        if isinstance(data_or_path, (bytes, bytearray)):
            z = zipfile.ZipFile(io.BytesIO(data_or_path))
            opf_bytes = _read_opf_from_zip(z)
        else:
            z = zipfile.ZipFile(data_or_path)
            opf_bytes = _read_opf_from_zip(z)
        if not opf_bytes:
            return None
        return _parse_opf_bytes(opf_bytes)
    except Exception:
        return None

# -----------------------
# Telegram send helpers (aceptan bytes o ruta a archivo)
# -----------------------
async def send_photo_bytes(bot, chat_id, caption, data_or_path, filename="photo.jpg"):
    """
    data_or_path: bytes o path a file. Returns telegram.Message or None.
    """
    if not data_or_path:
        return None
    try:
        # Envío desde bytes -> InputFile con filename para preservar nombre
        if isinstance(data_or_path, (bytes, bytearray)):
            bio = io.BytesIO(data_or_path)
            bio.name = filename
            bio.seek(0)
            input_file = InputFile(bio, filename=filename)
            return await bot.send_photo(chat_id=chat_id, photo=input_file, caption=caption)

        # Envío desde fichero en disco -> abrir, envolver en InputFile y cerrar descriptor
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

async def send_doc_bytes(bot, chat_id, caption, data_or_path, filename="file.epub"):
    """
    data_or_path: bytes o ruta a fichero. Devuelve telegram.Message o None.
    Asegura que Telegram reciba el nombre del archivo.
    """
    if not data_or_path:
        return None
    try:
        # Envío desde bytes en memoria -> envolver en InputFile con filename
        if isinstance(data_or_path, (bytes, bytearray)):
            bio = io.BytesIO(data_or_path)
            bio.name = filename
            bio.seek(0)
            input_file = InputFile(bio, filename=filename)
            return await bot.send_document(chat_id=chat_id, document=input_file, caption=caption)

        # Envío desde fichero en disco -> abrir, enviar y cerrar el descriptor
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

# -----------------------
# OPDS helpers (async)
# -----------------------
async def obtener_sinopsis_opds(series_id: str):
    if not series_id:
        return None
    url = f"{OPDS_ROOT_EVIL}/series/{series_id}"
    data = await fetch_bytes(url, timeout=10)
    if not data:
        return None
    try:
        root = ET.fromstring(data if isinstance(data, (bytes, bytearray)) else open(data, "rb").read())
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        summary_elem = root.find(".//atom:summary", ns)
        if summary_elem is not None and summary_elem.text:
            return " ".join(summary_elem.text.split())
    except Exception as e:
        logging.error("Error obteniendo sinopsis OPDS: %s", e)
    finally:
        _cleanup_tmp(data)
    return None

async def obtener_sinopsis_opds_volumen(series_id: str, volume_id: str):
    url = f"{OPDS_ROOT_EVIL}/series/{series_id}"
    data = await fetch_bytes(url, timeout=10)
    if not data:
        return None
    try:
        root = ET.fromstring(data if isinstance(data, (bytes, bytearray)) else open(data, "rb").read())
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            for link in entry.findall("atom:link", ns):
                href = link.attrib.get("href", "")
                if f"/volume/{volume_id}/" in href:
                    summary_elem = entry.find("atom:summary", ns)
                    if summary_elem is not None and summary_elem.text:
                        texto = summary_elem.text.strip()
                        if "Summary:" in texto:
                            texto = texto.split("Summary:", 1)[1].strip()
                        return limpiar_html_basico(texto)
    except Exception as e:
        logging.error("Error obteniendo sinopsis volumen: %s", e)
    finally:
        _cleanup_tmp(data)
    return None

async def obtener_metadatos_opds(series_id: str, volume_id: str):
    url = f"{OPDS_ROOT_EVIL}/series/{series_id}"
    datos = {
        "titulo_serie": None,
        "titulo_volumen": None,
        "autor": None,
        "ilustrador": None,
        "generos": [],
        "tags": [],
        "categoria": None,
        "demografia": None
    }
    data = await fetch_bytes(url, timeout=10)
    if not data:
        return datos
    try:
        root = ET.fromstring(data if isinstance(data, (bytes, bytearray)) else open(data, "rb").read())
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "dc": "http://purl.org/dc/terms/"
        }
        feed_title = root.find("atom:title", ns)
        if feed_title is not None and feed_title.text:
            titulo_serie = feed_title.text.strip()
            datos["titulo_serie"] = titulo_serie
            titulo_lower = titulo_serie.lower()
            if "[nl]" in titulo_lower:
                datos["categoria"] = "Novela ligera"
            elif "[nw]" in titulo_lower:
                datos["categoria"] = "Novela web"
            else:
                datos["categoria"] = "Desconocida"

        for entry in root.findall("atom:entry", ns):
            for link in entry.findall("atom:link", ns):
                href = link.attrib.get("href", "")
                if f"/volume/{volume_id}/" in href:
                    vol_title = entry.find("atom:title", ns)
                    if vol_title is not None and vol_title.text:
                        datos["titulo_volumen"] = vol_title.text.strip()
                    author_elem = entry.find("atom:author/atom:name", ns)
                    if author_elem is not None and author_elem.text:
                        datos["autor"] = author_elem.text.strip()
                    for cat in entry.findall("atom:category", ns):
                        term = cat.attrib.get("term", "").strip()
                        scheme = cat.attrib.get("scheme", "").lower()
                        if "genre" in scheme:
                            datos["generos"].append(term)
                        elif "tag" in scheme:
                            datos["tags"].append(term)
                        elif "demographic" in scheme:
                            datos["demografia"] = term
                        elif "category" in scheme and not datos["categoria"]:
                            datos["categoria"] = term
                    for creator in entry.findall("dc:creator", ns):
                        role = creator.attrib.get("role", "").lower()
                        if "illustrator" in role or "artist" in role:
                            datos["ilustrador"] = creator.text.strip()
                    break
    except Exception as e:
        logging.error("Error obteniendo metadatos OPDS: %s", e)
    finally:
        _cleanup_tmp(data)
    return datos

def generar_slug_from_meta(meta: dict) -> str:
    """
    Genera un slug basado en meta['titulo_serie'] si existe.
    Si no hay título de serie, intenta con titulo_volumen y luego vacío.
    Normaliza quitando corchetes, guiones, comas, apóstrofes y los símbolos solicitados,
    y reemplaza espacios por guiones bajos.
    """
    titulo_serie = None
    if isinstance(meta, dict):
        titulo_serie = meta.get("titulo_serie") or meta.get("titulo_volumen")
    elif isinstance(meta, str):
        titulo_serie = meta

    if not titulo_serie:
        return ""

    base_titulo = titulo_serie.split(":", 1)[0].strip()
    base_titulo = re.sub(r"\[.*?\]", "", base_titulo)
    base_titulo = base_titulo.split("-", 1)[0].strip()
    base_titulo = base_titulo.replace(",", " ")
    # elimina apóstrofes ASCII y tipográficos y caracteres indeseados
    for ch in ("'", "’", "#", "・"):
        base_titulo = base_titulo.replace(ch, "")
    base_titulo = re.sub(r"\s+", " ", base_titulo).strip()
    slug = base_titulo.replace(" ", "_")
    return slug

def formatear_mensaje_portada(meta: dict) -> str:
    # safe getters
    slug = generar_slug_from_meta(meta)

    titulo_serie = meta.get("titulo_serie")
    if titulo_serie:
        base_titulo = titulo_serie.split(":", 1)[0].strip()
        base_titulo = re.sub(r"\[.*?\]", "", base_titulo)
        base_titulo = base_titulo.split("-", 1)[0].strip()
        base_titulo = base_titulo.replace(",", " ")
        for ch in ("'", "’", "#", "・"):
            base_titulo = base_titulo.replace(ch, "")
        base_titulo = re.sub(r"\s+", " ", base_titulo).strip()
        # El slug ya lo tenemos en 'slug'
    else:
        slug = slug or ""

    categoria = meta.get("categoria") or "Desconocida"
    generos_list = meta.get("generos") or []
    generos = ", ".join(generos_list) if generos_list else "Desconocido"
    demografia_list = meta.get("demografia") or []
    demografia = ", ".join(demografia_list) if demografia_list else "Desconocida"
    autor = meta.get("autor") or (meta.get("autores")[0] if meta.get("autores") else "Desconocido")
    ilustrador = meta.get("ilustrador") or "Desconocido"

    # Maquetadores: prefer list from meta; si no hay, caer en el valor por defecto #ZeePub
    maqus = meta.get("maquetadores") or []
    if not maqus:
        maqu_line = "Maquetado por: #ZeePub"
    else:
        maqu_line = "Maquetado por: " + " ".join(f"#{m.replace(' ', '')}" for m in maqus)

    # Traducción / fuente si existe
    traduccion_parts = []
    if meta.get("traductor"):
        traduccion_parts.append(meta["traductor"])
    if meta.get("publisher"):
        traduccion_parts.append(meta["publisher"])
    if meta.get("publisher_url"):
        traduccion_parts.append(meta["publisher_url"])
    traduccion_line = ""
    if traduccion_parts:
        traduccion_line = "Traducción: " + " − ".join(traduccion_parts)

    lines = [
        f"{meta.get('titulo_volumen') or ''}",
        f"#{slug}" if slug else "",
        "",
        maqu_line,
        f"Categoría: {categoria}",
        f"Demografía: {demografia}",
        f"Géneros: {generos}",
        f"Autor: {autor}",
        f"Ilustrador: {ilustrador}"
    ]
    if traduccion_line:
        lines.append(traduccion_line)

    # eliminar líneas vacías accidentales
    lines = [l for l in lines if l is not None]
    return "\n".join(lines)

# -----------------------
# Bot handlers (async)
# -----------------------
async def mostrar_colecciones(update, context: ContextTypes.DEFAULT_TYPE, url: str, from_collection: bool = False):
    uid = update.effective_user.id
    ensure_user(uid)
    feed = await parse_feed_from_url(url)
    if not feed or not getattr(feed, "entries", []):
        msg = "❌ No se pudo leer el feed o no hay resultados."
        if getattr(update, "message", None):
            await update.message.reply_text(msg)
        else:
            await update.callback_query.edit_message_text(msg)
        return

    root_url = user_state.get(uid, {}).get("opds_root", OPDS_ROOT_START)

    # NOTE: auto-entry removed on purpose.
    # Anteriormente aquí había una auto-entrada que abría directamente ZeePubs en la primera carga del root.
    # La hemos eliminado para que el menú raíz (incluyendo "Añadido recientemente", "Actualizado recientemente"
    # y el botón "📚 Ingresar a Biblioteca") se muestre siempre al usar /start.
    # Si el usuario pulsa "📚 Ingresar a Biblioteca" se seguirá llamando a `abrir_zeepubs`
    # que busca la subsección de ZeePubs y entra directamente al contenido.

    user_state[uid]["ultima_pagina"] = url
    if from_collection:
        titulo_actual = user_state[uid].get("titulo", getattr(feed, "feed", {}).get("title", ""))
        url_actual = user_state[uid].get("url", root_url)
        user_state[uid]["historial"].append((titulo_actual, url_actual))

    user_state[uid]["url"] = url
    user_state[uid]["libros"] = {}
    user_state[uid]["colecciones"] = {}
    user_state[uid]["nav"] = {"prev": None, "next": None}

    colecciones = []
    libros = []

    for link in getattr(feed.feed, "links", []):
        rel = getattr(link, "rel", "")
        href = abs_url(BASE_URL, link.href)
        if rel == "next":
            user_state[uid]["nav"]["next"] = href
        elif rel == "previous":
            user_state[uid]["nav"]["prev"] = href

    if not user_state[uid]["nav"]["prev"] and user_state[uid]["historial"]:
        _, prev_url = user_state[uid]["historial"][-1]
        user_state[uid]["nav"]["prev"] = prev_url

    ocultar_titulos = {"En el puente", "Listas de lectura", "Deseo leer", "Todas las colecciones"}

    for entry in feed.entries:
        datos_libro = {"titulo": entry.title, "autor": getattr(entry, "author", "Desconocido")}
        try:
            datos_libro["href"] = getattr(entry, "link", "")
        except Exception:
            pass
        tiene_sub = False
        tiene_libro = False
        href_sub = None
        for link in getattr(entry, "links", []):
            rel = getattr(link, "rel", "")
            href = abs_url(BASE_URL, link.href)
            if rel == "subsection":
                tiene_sub = True
                href_sub = href
            if "acquisition" in rel:
                tiene_libro = True
                datos_libro["descarga"] = href
            if "image" in rel:
                datos_libro["portada"] = href
        if tiene_sub:
            if entry.title.strip() not in ocultar_titulos:
                colecciones.append({"titulo": entry.title, "href": href_sub})
        elif tiene_libro:
            libros.append(datos_libro)

    keyboard = []
    keyboard.append([InlineKeyboardButton("🔍 Buscar EPUB", callback_data="buscar")])

    if colecciones:
        for idx, col in enumerate(colecciones):
            user_state[uid]["colecciones"][idx] = col
            titulo_normalizado = col["titulo"].strip().lower()
            if titulo_normalizado == "todas las bibliotecas":
                if user_state.get(uid, {}).get("opds_root_base") != OPDS_ROOT_EVIL:
                    keyboard.append([InlineKeyboardButton("📚 Ingresar a Biblioteca", callback_data="abrir_zeepubs")])
                else:
                    keyboard.append([InlineKeyboardButton(col["titulo"], callback_data=f"col|{idx}")])
            else:
                keyboard.append([InlineKeyboardButton(col["titulo"], callback_data=f"col|{idx}")])
    elif libros:
        for idx, libro in enumerate(libros):
            user_state[uid]["libros"][idx] = libro
            nombre_archivo = os.path.basename(urlparse(libro.get("descarga", "")).path)
            nombre_archivo = unquote(nombre_archivo)
            volumen = nombre_archivo.replace(".epub", "").strip()
            keyboard.append([InlineKeyboardButton(volumen, callback_data=f"lib|{idx}")])

    nav_buttons = []
    if user_state[uid]["nav"]["prev"]:
        nav_buttons.append(InlineKeyboardButton("Pág. Anterior", callback_data="nav|prev"))
    if user_state[uid]["nav"]["next"]:
        nav_buttons.append(InlineKeyboardButton("Pág. Siguiente", callback_data="nav|next"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    titulo_mostrar = user_state[uid].get("titulo", getattr(feed.feed, "title", ""))
    reply_markup = InlineKeyboardMarkup(keyboard)
    if getattr(update, "message", None):
        await update.message.reply_text(titulo_mostrar, reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(titulo_mostrar, reply_markup=reply_markup)

async def entrar_directo_zeepubs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Intentar entrar directamente a ZeePubs [ES] a partir del OPDS root del usuario.
    """
    uid = update.effective_user.id
    ensure_user(uid)
    root_url = user_state.get(uid, {}).get("opds_root", OPDS_ROOT_START)
    logging.debug("entrar_directo_zeepubs: uid=%s root_url=%s", uid, root_url)

    feed = await parse_feed_from_url(root_url)
    if not feed:
        logging.debug("entrar_directo_zeepubs: no se pudo parsear feed desde %s", root_url)
        await mostrar_colecciones(update, context, root_url, from_collection=False)
        return

    # Mostrar título del feed y previsualizar entradas (debug)
    feed_title = getattr(feed, "feed", {}).get("title", None)
    logging.debug("entrar_directo_zeepubs: feed.title=%r, entries=%d", feed_title, len(getattr(feed, "entries", [])))

    destino_href = find_zeepubs_destino(feed)

    # Si no encontramos la subsección en el root actual, reintentar con el root público principal
    if not destino_href and root_url != OPDS_ROOT_START:
        logging.debug("entrar_directo_zeepubs: reintentando con OPDS_ROOT_START %s", OPDS_ROOT_START)
        feed_root_prim = await parse_feed_from_url(OPDS_ROOT_START)
        if feed_root_prim:
            logging.debug("entrar_directo_zeepubs: root principal feed.title=%r entries=%d", getattr(feed_root_prim, "feed", {}).get("title", None), len(getattr(feed_root_prim, "entries", [])))
            destino_href = find_zeepubs_destino(feed_root_prim)

    if destino_href:
        logging.debug("entrar_directo_zeepubs: destino encontrado %s", destino_href)
        user_state[uid]["titulo"] = "📁 ZeePubs [ES]"
        user_state[uid]["historial"] = []
        user_state[uid]["libros"] = {}
        user_state[uid]["colecciones"] = {}
        user_state[uid]["nav"] = {"prev": None, "next": None}
        await mostrar_colecciones(update, context, destino_href, from_collection=True)
        return

    logging.debug("entrar_directo_zeepubs: no se encontró ZeePubs, mostrando root %s", root_url)
    await mostrar_colecciones(update, context, root_url, from_collection=False)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    root_url = OPDS_ROOT_START
    ensure_user(uid)
    # Inicializar estado del usuario para el root público y mostrar el menú raíz
    user_state[uid].update({
        "titulo": "📚 Todas las bibliotecas",
        "destino": update.effective_chat.id,
        "chat_origen": update.effective_chat.id,
        "ultima_pagina": root_url,
        "opds_root": root_url,
        "opds_root_base": root_url,
        "auto_enter_done": False
    })
    # Mostrar el menú raíz (no entrar automáticamente). El botón "📚 Ingresar a Biblioteca"
    # seguirá llamando a `abrir_zeepubs` que abre ZeePubs directamente.
    await mostrar_colecciones(update, context, root_url, from_collection=False)

async def evil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    root_url = OPDS_ROOT_EVIL
    ensure_user(uid)
    user_state[uid].update({
        "titulo": "📚 Todas las bibliotecas",
        "destino": None,
        "chat_origen": update.effective_chat.id,
        "esperando_password": True,
        "ultima_pagina": root_url,
        "opds_root": root_url,
        "opds_root_base": root_url
    })
    await update.message.reply_text("🔒 Ingresa la contraseña para acceder a este modo:")

async def recibir_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    texto = update.message.text.strip()
    if user_state.get(uid, {}).get("esperando_password"):
        if texto == get_six_hour_password():
            user_state[uid]["esperando_password"] = False
            keyboard = [
                [InlineKeyboardButton("📍 Publicar aquí", callback_data="destino|aqui")],
                [InlineKeyboardButton("📢 ZeePubBotTest", callback_data="destino|@ZeePubBotTest")],
                [InlineKeyboardButton("📢 ZeePubs", callback_data="destino|@ZeePubs")],
                [InlineKeyboardButton("✏️ Otro destino", callback_data="destino|otro")]
            ]
            await update.message.reply_text(
                "✅ Contraseña correcta. ¿Dónde quieres publicar los libros?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            user_state[uid]["esperando_password"] = False
            await update.message.reply_text("❌ Contraseña incorrecta. Volviendo al modo normal…")
            await start(update, context)
        return

    if user_state.get(uid, {}).get("esperando_destino_manual"):
        # Usuario escribió un destino manual; guardarlo y mostrar colecciones para navegar
        user_state[uid]["destino"] = texto
        user_state[uid]["esperando_destino_manual"] = False

        # Usar el OPDS root actual del usuario
        root = user_state[uid].get("opds_root", OPDS_ROOT_START)
        # Ajustar título según root (mejora UX)
        if root == OPDS_ROOT_EVIL:
            user_state[uid]["titulo"] = "📁 ZeePubs [ES]"
        else:
            user_state[uid]["titulo"] = "📚 Todas las bibliotecas"

        # Mostrar colecciones inmediatamente para que el usuario pueda elegir libros
        await mostrar_colecciones(update, context, root, from_collection=False)

    elif user_state.get(uid, {}).get("esperando_busqueda"):
        user_state[uid]["esperando_busqueda"] = False
        search_url = build_search_url(texto, uid)
        feed = await parse_feed_from_url(search_url)
        if not feed or not getattr(feed, "entries", []):
            keyboard = [
                [InlineKeyboardButton("🔄 Volver a buscar", callback_data="buscar")],
                [InlineKeyboardButton("📚 Ir a colecciones", callback_data="volver_colecciones")]
            ]
            await update.message.reply_text(
                f"🔍 No se encontraron resultados para: {texto}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await mostrar_colecciones(update, context, search_url, from_collection=False)

async def set_destino(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    ensure_user(uid)
    _, destino = query.data.split("|", 1)

    if destino == "aqui":
        # Publicar en el chat actual: además mostramos la lista de colecciones
        user_state[uid]["destino"] = update.effective_chat.id

        # Usar el OPDS root que tenga el usuario (si previamente entró a 'evil' será OPDS_ROOT_EVIL)
        root = user_state[uid].get("opds_root", OPDS_ROOT_START)

        # Actualizar título visible (opcional, mejora UX)
        if root == OPDS_ROOT_EVIL:
            user_state[uid]["titulo"] = "📁 ZeePubs [ES]"
        else:
            user_state[uid]["titulo"] = "📚 Todas las bibliotecas"

        # Mostrar colecciones directamente en el root actual
        await mostrar_colecciones(update, context, root, from_collection=False)

    elif destino in ["@ZeePubBotTest", "@ZeePubs"]:
        # Guardar destino remoto y mostrar colecciones para que el usuario pueda elegir libros
        user_state[uid]["destino"] = destino

        root = user_state[uid].get("opds_root", OPDS_ROOT_START)
        if root == OPDS_ROOT_EVIL:
            user_state[uid]["titulo"] = "📁 ZeePubs [ES]"
        else:
            user_state[uid]["titulo"] = "📚 Todas las bibliotecas"

        await mostrar_colecciones(update, context, root, from_collection=False)

    elif destino == "otro":
        user_state[uid]["esperando_destino_manual"] = True
        await query.edit_message_text("Escribe el @usuario o chat_id donde quieres publicar:")

async def elegir_modo(target_message, uid, query=None):
    """
    Mensaje para elegir destino / acciones posteriores.
    Eliminado el selector de 'modo' — solo se ofrece búsqueda o acciones relacionadas.
    """
    ensure_user(uid)
    keyboard = [
        [InlineKeyboardButton("🔍 Buscar EPUB", callback_data="buscar")]
    ]
    texto = (
        f"Destino configurado: {user_state[uid]['destino']}\n\n"
        "Puedes buscar un libro o continuar:"
    )
    if query:
        await query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await target_message.reply_text(texto, reply_markup=InlineKeyboardMarkup(keyboard))

async def buscar_epub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    ensure_user(uid)
    user_state[uid]["esperando_busqueda"] = True
    await query.edit_message_text("Escribe el título o parte del título del EPUB que quieres buscar:")

async def abrir_zeepubs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id

    root_url = user_state.get(uid, {}).get("opds_root", OPDS_ROOT_START)

    def norm(s: str) -> str:
        return " ".join((s or "").split()).casefold()

    feed_root = await parse_feed_from_url(root_url)
    destino_href = None

    if feed_root and getattr(feed_root, "entries", []):
        for entry in feed_root.entries:
            if "zeepubs" in norm(getattr(entry, "title", "")):
                for link in getattr(entry, "links", []):
                    if getattr(link, "rel", "") == "subsection":
                        destino_href = abs_url(BASE_URL, link.href)
                        break
            if destino_href:
                break

    # fallback: buscar en "Todas las bibliotecas"
    if not destino_href:
        biblios_href = None
        for entry in feed_root.entries:
            if "todas las bibliotecas" in norm(getattr(entry, "title", "")):
                for link in getattr(entry, "links", []):
                    if getattr(link, "rel", "") == "subsection":
                        biblios_href = abs_url(BASE_URL, link.href)
                        break
        if biblios_href:
            feed_biblios = mostrar_feed(biblios_href)
            if feed_biblios and getattr(feed_biblios, "entries", []):
                for entry in feed_biblios.entries:
                    if "zeepubs" in norm(getattr(entry, "title", "")):
                        for link in getattr(entry, "links", []):
                            if getattr(link, "rel", "") == "subsection":
                                destino_href = abs_url(BASE_URL, link.href)
                                break
                    if destino_href:
                        break

    if destino_href:
        user_state[uid]["titulo"] = "📁 ZeePubs"
        user_state[uid]["historial"] = []
        user_state[uid]["libros"] = {}
        user_state[uid]["colecciones"] = {}
        user_state[uid]["nav"] = {"prev": None, "next": None}
        await mostrar_colecciones(update, context, destino_href, from_collection=True)
    else:
        await query.answer("No se pudo abrir la biblioteca directamente. Intenta entrar manualmente.", show_alert=False)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = update.effective_user.id
    ensure_user(uid)
    if data.startswith("col|"):
        idx = int(data.split("|")[1])
        col = user_state[uid]["colecciones"].get(idx)
        if col:
            user_state[uid]["titulo"] = f"📁 {col['titulo']}"
            await mostrar_colecciones(update, context, col["href"], from_collection=True)
    elif data.startswith("lib|"):
        idx = int(data.split("|")[1])
        libro = user_state[uid]["libros"].get(idx)
        if libro:
            descarga = str(libro.get("descarga", ""))
            href = str(libro.get("href", ""))
            m = re.search(r'/series/(\d+)/volume/(\d+)/', descarga) or re.search(r'/series/(\d+)/volume/(\d+)/', href)
            if m:
                user_state[uid]["series_id"] = m.group(1)
                user_state[uid]["volume_id"] = m.group(2)
                logging.info("DEBUG series_id: %s volume_id: %s", user_state[uid]['series_id'], user_state[uid]['volume_id'])
            else:
                m2 = re.search(r'/series/(\d+)', descarga) or re.search(r'/series/(\d+)', href)
                if m2:
                    user_state[uid]["series_id"] = m2.group(1)
                    logging.info("DEBUG series_id: %s", user_state[uid]['series_id'])
                else:
                    logging.warning("DEBUG: No se encontraron IDs en URLs del libro")
            user_state[uid]["ultima_pagina"] = href or descarga

            # Determinar destino real usado (si user_state['destino'] es falsy, publicar_libro usa chat_origen)
            chat_origen = user_state[uid].get("chat_origen")
            actual_destino = user_state[uid].get("destino") or chat_origen

            # Si publicamos en el mismo chat donde está el menú, borrar el mensaje del menú
            # y mostrar un mensaje temporal "⏳ Preparando..." que se eliminará cuando se publique la portada.
            menu_prep = None
            if actual_destino == chat_origen:
                try:
                    # eliminar el mensaje con el inline keyboard (menú)
                    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=query.message.message_id)
                except Exception:
                    logging.debug("No se pudo borrar el mensaje del menú (quizá ya eliminado)")

                try:
                    prep_msg = await context.bot.send_message(chat_id=chat_origen, text="⏳ Preparando...")
                    prep_msg_id = getattr(prep_msg, "message_id", None)
                    if prep_msg_id:
                        menu_prep = (chat_origen, prep_msg_id)
                except Exception as e:
                    logging.debug("No se pudo enviar mensaje 'Preparando...': %s", e)
                    menu_prep = None

            # Publicar el libro (sube/manda el EPUB), pasando menu_prep para que se borre cuando corresponda
            await publicar_libro(update, context, uid, libro["titulo"], libro.get("portada", ""), libro.get("descarga", ""), menu_prep=menu_prep)

            # Si publicamos en otro destino, informar editando el menú original (comportamiento previo)
            if actual_destino != chat_origen:
                try:
                    await query.edit_message_text(f"✅ Publicado: {libro['titulo']}")
                except Exception:
                    logging.debug("Error al editar mensaje de confirmación de publicación")
    elif data.startswith("nav|"):
        direction = data.split("|")[1]
        href = user_state[uid]["nav"].get(direction)
        if href:
            await mostrar_colecciones(update, context, href, from_collection=False)
        else:
            await query.answer("No hay más páginas en esa dirección.", show_alert=False)
    elif data == "back":
        if user_state[uid]["historial"]:
            titulo_prev, url_prev = user_state[uid]["historial"].pop()
            user_state[uid]["titulo"] = titulo_prev
            await mostrar_colecciones(update, context, url_prev, from_collection=False)
        else:
            await query.answer("No hay nivel anterior disponible.", show_alert=False)
    elif data == "volver_colecciones":
        msg_id = user_state.get(uid, {}).pop("msg_que_hacer", None)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except Exception:
                pass
        root_base = user_state.get(uid, {}).get("opds_root_base", OPDS_ROOT_START)
        user_state[uid]["opds_root"] = root_base
        await mostrar_colecciones(update, context, root_base, from_collection=False)
    elif data == "volver_ultima":
        msg_id = user_state.get(uid, {}).pop("msg_que_hacer", None)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except Exception:
                pass
        root_url = user_state.get(uid, {}).get("opds_root", OPDS_ROOT_START)
        ultima_url = user_state[uid].get("ultima_pagina", root_url)
        await mostrar_colecciones(update, context, ultima_url, from_collection=False)
    elif data == "cerrar":
        msg_id = user_state.get(uid, {}).pop("msg_que_hacer", None)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except Exception:
                pass
        await query.edit_message_text("👋 ¡Gracias por usar el bot! Hasta la próxima.")

async def volver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    if user_state.get(uid, {}).get("historial"):
        titulo_prev, url_prev = user_state[uid]["historial"].pop()
        user_state[uid]["titulo"] = titulo_prev
        await mostrar_colecciones(update, context, url_prev, from_collection=False)
    else:
        await update.message.reply_text("No hay nivel anterior disponible.")

async def publicar_libro(update_or_uid, context, uid: int, titulo: str, portada_url: str, epub_url: str, menu_prep: tuple = None):
    """
    Publica un libro: implementación única (equivalente al antiguo 'clasico').
    Parámetros nuevos:
      - menu_prep: Optional[tuple(chat_id, message_id)] mensaje temporal 'Preparando...' en el chat del menú
                   que debe borrarse cuando se publique la portada (o al final como fallback).
    """
    bot = context.bot
    ensure_user(uid)
    destino = user_state[uid].get("destino") or user_state[uid].get("chat_origen")
    chat_origen = user_state[uid].get("chat_origen")
    series_id = user_state[uid].get("series_id")
    volume_id = user_state[uid].get("volume_id")
    root_url = user_state[uid].get("opds_root", OPDS_ROOT_START)
    ultima_url = user_state[uid].get("url", root_url)
    user_state[uid]["ultima_pagina"] = ultima_url

    # Obtener metadatos OPDS primeramente
    meta = await obtener_metadatos_opds(series_id, volume_id)

    # Si hay epub disponible, descárgalo primero para extraer content.opf y enriquecer metadata.
    epub_downloaded = None
    if epub_url:
        epub_downloaded = await fetch_bytes(epub_url, timeout=120)
        if epub_downloaded:
            try:
                opf_meta = await parse_opf_from_epub(epub_downloaded)
                if opf_meta:
                    # Integrar opf_meta en meta (priorizar opf cuando exista)
                    if opf_meta.get("titulo_volumen"):
                        meta["titulo_volumen"] = opf_meta["titulo_volumen"]
                    if opf_meta.get("titulo_serie"):
                        meta["titulo_serie"] = opf_meta["titulo_serie"]
                    if opf_meta.get("autores"):
                        meta["autor"] = opf_meta["autores"][0] if opf_meta["autores"] else meta.get("autor")
                        meta["autores"] = opf_meta["autores"]
                    if opf_meta.get("ilustrador"):
                        meta["ilustrador"] = opf_meta["ilustrador"]
                    # agregar géneros nuevos
                    if opf_meta.get("generos"):
                        for g in opf_meta.get("generos", []):
                            if g not in meta["generos"]:
                                meta["generos"].append(g)
                    # demografía / categoria
                    if opf_meta.get("demografia"):
                        meta["demografia"] = opf_meta.get("demografia")
                    if opf_meta.get("categoria"):
                        meta["categoria"] = opf_meta.get("categoria")
                    # maquetadores / traductor / publisher info
                    if opf_meta.get("maquetadores"):
                        meta.setdefault("maquetadores", []).extend(x for x in opf_meta.get("maquetadores", []) if x not in meta.get("maquetadores", []))
                    if opf_meta.get("traductor"):
                        meta["traductor"] = opf_meta.get("traductor")
                    if opf_meta.get("publisher"):
                        meta["publisher"] = opf_meta.get("publisher")
                    if opf_meta.get("publisher_url"):
                        meta["publisher_url"] = opf_meta.get("publisher_url")
            except Exception as e:
                logging.debug("Error parseando OPF: %s", e)

    # calcular slug una vez integrado meta (si es posible)
    slug = generar_slug_from_meta(meta)

    mensaje_portada = formatear_mensaje_portada(meta)

    # Enviar portada con el mensaje (si existe)
    if portada_url:
        result = await fetch_bytes(portada_url, timeout=15)
        try:
            sent_photo = await send_photo_bytes(bot, destino, mensaje_portada, result, filename="portada.jpg")
            # Si se pasó menu_prep (mensaje "Preparando..." en el menú), eliminarlo ahora que la portada fue enviada
            if menu_prep and isinstance(menu_prep, tuple):
                try:
                    menu_chat, menu_msg_id = menu_prep
                    if menu_chat and menu_msg_id:
                        await bot.delete_message(chat_id=menu_chat, message_id=menu_msg_id)
                except Exception:
                    logging.debug("No se pudo borrar el mensaje 'Preparando...' en el menú")
        finally:
            _cleanup_tmp(result)
    else:
        # No hay portada: como fallback, borrar igualmente el menu_prep si existe al final del flujo.
        pass

    # Sinopsis (primer intento por volumen, si falla por serie)
    sinopsis_texto = None
    if series_id and volume_id:
        sinopsis_texto = await obtener_sinopsis_opds_volumen(series_id, volume_id)
    if not sinopsis_texto and series_id:
        try:
            sinopsis_texto = await obtener_sinopsis_opds(series_id)
        except Exception as e:
            logging.error("Error obteniendo sinopsis por serie: %s", e)

    if sinopsis_texto:
        sinopsis_esc = html.escape(sinopsis_texto)
        # Añadir slug fuera del blockquote si existe
        sinopsis_suffix = f"\n#{slug}" if slug else ""
        mensaje = f"<b>Sinopsis:</b>\n<blockquote>{sinopsis_esc}</blockquote>{sinopsis_suffix}"
        await bot.send_message(chat_id=destino, text=mensaje, parse_mode="HTML")
    else:
        # si no hay sinopsis, aún podemos poner el slug
        if slug:
            await bot.send_message(chat_id=destino, text=f"Sinopsis: (no disponible)\n#{slug}")
        else:
            await bot.send_message(chat_id=destino, text="Sinopsis: (no disponible)")

    prep = await bot.send_message(chat_id=destino, text="⏳ Preparando archivo...")
    prep_msg_id = getattr(prep, "message_id", None)

    # Envío del EPUB: usa epub_downloaded si lo obtuvimos, sino descarga ahora
    epub_to_send = epub_downloaded
    if not epub_to_send and epub_url:
        epub_to_send = await fetch_bytes(epub_url, timeout=120)

    if epub_to_send:
        try:
            nombre_archivo = os.path.basename(urlparse(epub_url).path) or "archivo.epub"
            nombre_archivo = unquote(nombre_archivo)
            caption = titulo + (f"\n#{slug}" if slug else "")
            await send_doc_bytes(bot, destino, caption, epub_to_send, filename=nombre_archivo)
        finally:
            _cleanup_tmp(epub_to_send)

    # borrar el mensaje prep en destino
    if prep_msg_id:
        try:
            await bot.delete_message(chat_id=destino, message_id=prep_msg_id)
        except Exception:
            pass

    # Como fallback final, si aún existe el menu_prep (por ejemplo no había portada),
    # intentar borrarlo ahora para no dejar mensajes huérfanos.
    if menu_prep and isinstance(menu_prep, tuple):
        try:
            menu_chat, menu_msg_id = menu_prep
            if menu_chat and menu_msg_id:
                await bot.delete_message(chat_id=menu_chat, message_id=menu_msg_id)
        except Exception:
            # ya eliminado o imposible de borrar; no fatal
            pass

    # Menú opciones (enviar al chat de origen)
    keyboard = [
        [InlineKeyboardButton("📚 Volver a categorías", callback_data="volver_colecciones")],
        [InlineKeyboardButton("↩️ Volver a la página anterior", callback_data="volver_ultima")],
        [InlineKeyboardButton("❌ Cerrar", callback_data="cerrar")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg_temp = await bot.send_message(chat_id=chat_origen, text="¿Qué quieres hacer ahora?")
    msg_temp_id = getattr(msg_temp, "message_id", None)
    user_state[uid]["msg_que_hacer"] = msg_temp_id
    await bot.send_message(chat_id=chat_origen, text="Selecciona una opción:", reply_markup=reply_markup)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /cancel - Cierra la última ventana de selección y restablece el estado del usuario
    al estado inicial mínimo (listo para usar /start o /evil).
    """
    uid = update.effective_user.id
    ensure_user(uid)

    # Intentar borrar el mensaje guardado en user_state[uid]['msg_que_hacer']
    msg_id = user_state[uid].pop("msg_que_hacer", None)
    chat_id = None
    # Preferir el chat de la actualización si está disponible
    try:
        chat_id = update.effective_chat.id
    except Exception:
        chat_id = None

    if msg_id and chat_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            # no fatal si no pudo borrarse
            logging.debug("cancel: no se pudo borrar msg_que_hacer (chat=%s msg=%s)", chat_id, msg_id)

    # También intentar borrar cualquier prep/menu temporales conocidos (menu_prep) si existen
    menu_prep = user_state[uid].pop("menu_prep", None)
    if menu_prep and isinstance(menu_prep, tuple):
        try:
            _chat, _msg = menu_prep
            if _chat and _msg:
                await context.bot.delete_message(chat_id=_chat, message_id=_msg)
        except Exception:
            logging.debug("cancel: no se pudo borrar menu_prep %r", menu_prep)

    # Restablecer estado del usuario a valores iniciales mínimos
    user_state[uid].update({
        "historial": [],
        "libros": {},
        "colecciones": {},
        "nav": {"prev": None, "next": None},
        "titulo": "📚 Todas las bibliotecas",
        "destino": None,
        "chat_origen": None,
        "esperando_destino_manual": False,
        "esperando_busqueda": False,
        "esperando_password": False,
        "ultima_pagina": None,
        "opds_root": OPDS_ROOT_START,
        "opds_root_base": OPDS_ROOT_START,
        "series_id": None,
        "volume_id": None,
        "msg_que_hacer": None
    })

    # Confirmación al usuario
    try:
        if chat_id:
            await context.bot.send_message(chat_id=chat_id, text="✅ Operación cancelada. El bot está listo. Usa /start para comenzar.")
        else:
            # Fallback: usar update.message si existe
            if getattr(update, "message", None):
                await update.message.reply_text("✅ Operación cancelada. El bot está listo. Usa /start para comenzar.")
    except Exception:
        # Silenciar errores en la confirmación
        logging.debug("cancel: no se pudo enviar mensaje de confirmación")

# -----------------------
# Start bot
# -----------------------
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CallbackQueryHandler(set_destino, pattern="^destino\\|"))
    app.add_handler(CallbackQueryHandler(buscar_epub, pattern="^buscar$"))
    app.add_handler(CallbackQueryHandler(abrir_zeepubs, pattern="^abrir_zeepubs$"))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("evil", evil))
    app.add_handler(CommandHandler("volver", volver))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_texto))

    try:
        app.run_polling()
    finally:
        # Close global aiohttp session cleanly when app stops
        if _GLOBAL_AIOSESSION is not None:
            try:
                asyncio.run(_GLOBAL_AIOSESSION.close())
            except Exception as e:
                logging.debug("Error closing aiohttp session: %s", e)
