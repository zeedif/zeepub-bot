import re
import os
import json
import requests
import feedparser
import hashlib
import datetime
import logging
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from urllib.parse import urljoin, urlparse, unquote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
import html  # para escapar texto en HTML parse_mode

# ===== CONFIGURACIÓN =====
load_dotenv()

BASE_URL = os.getenv("BASE_URL")
OPDS_ROOT_START = f"{BASE_URL}{os.getenv('OPDS_ROOT_START')}"
OPDS_ROOT_EVIL  = f"{BASE_URL}{os.getenv('OPDS_ROOT_EVIL')}"
KAVITA_API_KEY  = os.getenv("KAVITA_API_KEY")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")
SECRET_SEED     = os.getenv("SECRET_SEED")

user_state = {}

def get_six_hour_password():
    now = datetime.datetime.now()
    bloque = now.hour // 6
    raw = f"{SECRET_SEED}{now.year}-{now.month}-{now.day}-B{bloque}"
    return hashlib.sha256(raw.encode()).hexdigest()[:8]

def abs_url(base, href):
    return href if href.startswith("http") else urljoin(base, href)

def mostrar_feed(url):
    feed = feedparser.parse(url)
    return None if feed.bozo else feed

def build_search_url(query, uid=None):
    root = OPDS_ROOT_START  # valor por defecto
    if uid and uid in user_state:
        root = user_state[uid].get("opds_root", OPDS_ROOT_START)

    if "/series" in root:
        root_series = root.split("?")[0]
    else:
        root_series = f"{root}/series"
    return f"{root_series}?query={query}"

def obtener_sinopsis_opds(series_id):
    """Obtiene la sinopsis desde el feed OPDS de Kavita."""
    if not series_id:
        return None
    url = f"{OPDS_ROOT_EVIL}/series/{series_id}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            summary_elem = root.find(".//atom:summary", ns)
            if summary_elem is not None and summary_elem.text:
                return " ".join(summary_elem.text.split())
    except Exception as e:
        print(f"Error obteniendo sinopsis OPDS: {e}")
    return None

# === NUEVAS FUNCIONES ===
def limpiar_html_basico(texto_html: str) -> str:
    # Convierte <br/> en saltos de línea y elimina otras etiquetas HTML
    texto_html = texto_html.replace("<br/>", "\n").replace("<br>", "\n")
    texto_limpio = re.sub(r"<.*?>", "", texto_html)
    # Limpia líneas vacías redundantes
    return "\n".join([ln.rstrip() for ln in texto_limpio.strip().splitlines() if ln.strip()])

def obtener_sinopsis_opds_volumen(series_id, volume_id):
    """
    Busca en el OPDS de la serie la entry cuyo link de adquisición contenga /volume/{volume_id}/
    y devuelve el <summary> limpio.
    """
    url = f"{OPDS_ROOT_EVIL}/series/{series_id}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
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
        logging.error(f"Error obteniendo sinopsis volumen: {e}")
    return None

def obtener_metadatos_opds(series_id, volume_id):
    """
    Extrae metadatos de Kavita usando solo OPDS, igual que hacemos con la sinopsis.
    Devuelve un diccionario con título serie, título volumen, autor, ilustrador, géneros, etc.
    """
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

    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return datos

        root = ET.fromstring(r.content)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "dc": "http://purl.org/dc/terms/"
        }

        # Título de la serie
        feed_title = root.find("atom:title", ns)
        if feed_title is not None and feed_title.text:
            titulo_serie = feed_title.text.strip()
            datos["titulo_serie"] = titulo_serie

            # 🔹 Detectar categoría por etiqueta en el título
            titulo_lower = titulo_serie.lower()
            if "[nl]" in titulo_lower:
                datos["categoria"] = "Novela ligera"
            elif "[nw]" in titulo_lower:
                datos["categoria"] = "Novela web"
            else:
                datos["categoria"] = "Desconocida"

        # Recorrer entries para encontrar el volumen exacto
        for entry in root.findall("atom:entry", ns):
            for link in entry.findall("atom:link", ns):
                href = link.attrib.get("href", "")
                if f"/volume/{volume_id}/" in href:
                    # Título del volumen
                    vol_title = entry.find("atom:title", ns)
                    if vol_title is not None and vol_title.text:
                        datos["titulo_volumen"] = vol_title.text.strip()

                    # Autor principal
                    author_elem = entry.find("atom:author/atom:name", ns)
                    if author_elem is not None and author_elem.text:
                        datos["autor"] = author_elem.text.strip()

                    # Categorías (géneros, tags, demografía, etc.)
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

                    # Ilustrador (si viene como dc:creator con role)
                    for creator in entry.findall("dc:creator", ns):
                        role = creator.attrib.get("role", "").lower()
                        if "illustrator" in role or "artist" in role:
                            datos["ilustrador"] = creator.text.strip()

                    break  # ya encontramos el volumen, no seguir buscando

    except Exception as e:
        logging.error(f"Error obteniendo metadatos OPDS: {e}")

    return datos

import re

import re

def formatear_mensaje_portada(meta):
    # --- Construir slug limpio ---
    if meta["titulo_serie"]:
        # Cortar en ":" si existe
        base_titulo = meta["titulo_serie"].split(":", 1)[0].strip()
        # Eliminar cualquier contenido entre corchetes (ej: [NL], [NW], etc.)
        base_titulo = re.sub(r"\[.*?\]", "", base_titulo)
        # Cortar también en "-" si existe (para quitar subtítulos como " - Storyline")
        base_titulo = base_titulo.split("-", 1)[0].strip()
        # Reemplazar comas por espacios
        base_titulo = base_titulo.replace(",", " ")
        # Quitar espacios múltiples
        base_titulo = re.sub(r"\s+", " ", base_titulo).strip()
        # Reemplazar espacios por guiones bajos
        slug = base_titulo.replace(" ", "_")
    else:
        slug = ""

    # --- Categoría (ya calculada en obtener_metadatos_opds) ---
    categoria = meta["categoria"] or "Desconocida"

    # --- Géneros ---
    generos = ", ".join(meta["generos"]) if meta["generos"] else "Desconocido"

    return (
        f"{meta['titulo_volumen']}\n"
        f"#{slug}\n\n"
        f"Maquetado por: #ZeePub\n"
        f"Categoría: {categoria}\n"
        f"Demografía: {meta['demografia'] or 'Desconocida'}\n"
        f"Géneros: {generos}\n"
        f"Autor: {meta['autor'] or 'Desconocido'}\n"
        f"Ilustrador: {meta['ilustrador'] or 'Desconocido'}"
    )

# === NUEVA FUNCIÓN PARA ENTRAR DIRECTO A ZEEPUBS [ES] ===
async def entrar_directo_zeepubs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Usa el OPDS_ROOT definido para este usuario en user_state[uid]["opds_root"].
    Busca la entrada con título 'ZeePubs [ES]' y sigue su link 'subsection'.
    Si no la encuentra pero hay solo una biblioteca, entra a esa única.
    Como último recurso, cae de vuelta a mostrar_colecciones(root_url).
    """
    uid = update.effective_user.id
    root_url = user_state.get(uid, {}).get("opds_root", OPDS_ROOT_START)

    feed = mostrar_feed(root_url)
    if not feed or not getattr(feed, "entries", []):
        await mostrar_colecciones(update, context, root_url, from_collection=False)
        return

    destino_href = None
    for entry in feed.entries:
        if entry.title.strip() == "ZeePubs [ES]":
            for link in getattr(entry, "links", []):
                if getattr(link, "rel", "") == "subsection":
                    destino_href = abs_url(BASE_URL, link.href)
                    break
            if destino_href:
                break

    if not destino_href:
        candidatos = []
        for entry in feed.entries:
            for link in getattr(entry, "links", []):
                if getattr(link, "rel", "") == "subsection":
                    candidatos.append(abs_url(BASE_URL, link.href))
                    break
        if len(candidatos) == 1:
            destino_href = candidatos[0]

    if destino_href:
        user_state[uid]["titulo"] = "📁 ZeePubs [ES]"
        user_state[uid]["historial"] = []
        user_state[uid]["libros"] = {}
        user_state[uid]["colecciones"] = {}
        user_state[uid]["nav"] = {"prev": None, "next": None}
        await mostrar_colecciones(update, context, destino_href, from_collection=True)
        return

    await mostrar_colecciones(update, context, root_url, from_collection=False)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    root_url = OPDS_ROOT_START  # root para este comando
    user_state[uid] = {
        "historial": [],
        "libros": {},
        "colecciones": {},
        "nav": {"prev": None, "next": None},
        "titulo": "📚 Todas las bibliotecas",
        "destino": update.effective_chat.id,
        "chat_origen": update.effective_chat.id,
        "modo": "compacto",
        "esperando_destino_manual": False,
        "esperando_busqueda": False,
        "esperando_password": False,
        "ultima_pagina": root_url,
        "opds_root": root_url,           # URL actual de navegación
        "opds_root_base": root_url       # raíz del catálogo
    }
    await mostrar_colecciones(update, context, root_url, from_collection=False)

# /evil protegido
async def evil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    root_url = OPDS_ROOT_EVIL  # root para este comando
    user_state[uid] = {
        "historial": [],
        "libros": {},
        "colecciones": {},
        "nav": {"prev": None, "next": None},
        "titulo": "📚 Todas las bibliotecas",
        "destino": None,
        "chat_origen": update.effective_chat.id,
        "modo": None,
        "esperando_destino_manual": False,
        "esperando_busqueda": False,
        "esperando_password": True,
        "ultima_pagina": root_url,
        "opds_root": root_url,           # URL actual de navegación
        "opds_root_base": root_url       # raíz del catálogo
    }
    await update.message.reply_text("🔒 Ingresa la contraseña para acceder a este modo:")

async def recibir_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    texto = update.message.text.strip()

    # Contraseña /evil
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
        user_state[uid]["destino"] = texto
        user_state[uid]["esperando_destino_manual"] = False
        await elegir_modo(update.message, uid)

    elif user_state.get(uid, {}).get("esperando_busqueda"):
        user_state[uid]["esperando_busqueda"] = False
        # 🔹 Usar el root dinámico del usuario
        search_url = build_search_url(texto, uid)
        feed = mostrar_feed(search_url)
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
    _, destino = query.data.split("|", 1)

    if destino == "aqui":
        user_state[uid]["destino"] = update.effective_chat.id
        await elegir_modo(None, uid, query)

    elif destino in ["@ZeePubBotTest", "@ZeePubs"]:
        user_state[uid]["destino"] = destino
        await elegir_modo(None, uid, query)

    elif destino == "otro":
        user_state[uid]["esperando_destino_manual"] = True
        await query.edit_message_text("Escribe el @usuario o chat_id donde quieres publicar:")

async def elegir_modo(target_message, uid, query=None):
    keyboard = [
        [InlineKeyboardButton("📄 Modo completo", callback_data="modo|clasico")],
        [InlineKeyboardButton("📦 Modo compacto", callback_data="modo|compacto")],
        [InlineKeyboardButton("🔍 Buscar EPUB", callback_data="buscar")]
    ]
    texto = (
        f"Destino configurado: {user_state[uid]['destino']}\n\n"
        "Elige el modo de publicación o busca un libro:"
    )

    if query:
        await query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await target_message.reply_text(texto, reply_markup=InlineKeyboardMarkup(keyboard))

async def set_modo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    _, modo = query.data.split("|", 1)
    user_state[uid]["modo"] = modo

    # 🔹 Usar el root dinámico del usuario
    root_url = user_state.get(uid, {}).get("opds_root", OPDS_ROOT_START)
    await mostrar_colecciones(update, context, root_url, from_collection=False)

async def buscar_epub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    user_state[uid]["esperando_busqueda"] = True
    await query.edit_message_text("Escribe el título o parte del título del EPUB que quieres buscar:")

async def mostrar_colecciones(update, context, url, from_collection=False):
    feed = mostrar_feed(url)    
    if not feed or not getattr(feed, "entries", []):
        msg = "❌ No se pudo leer el feed o no hay resultados."
        if getattr(update, "message", None):
            await update.message.reply_text(msg)
        else:
            await update.callback_query.edit_message_text(msg)
        return
        
    uid = update.effective_user.id
    root_url = user_state.get(uid, {}).get("opds_root", OPDS_ROOT_START)  # ← root dinámico

    # === Auto-entrada a ZeePubs [ES] en la primera carga del root ===
    if (url == root_url and not from_collection and
        not user_state.get(uid, {}).get("auto_enter_done")):

        def norm(s): return " ".join(s.split()).casefold()  # normaliza espacios y mayúsculas
        destino_href = None

        # 1) Busca una entrada cuyo título sea ZeePubs [ES]
        for entry in feed.entries:
            if norm(getattr(entry, "title", "")) == norm("ZeePubs [ES]"):
                for link in getattr(entry, "links", []):
                    if getattr(link, "rel", "") == "subsection":
                        destino_href = abs_url(BASE_URL, link.href)
                        break
                if destino_href:
                    break

        # 2) Si no lo encuentra, y hay una sola subsección, entra a esa
        if not destino_href:
            candidatos = []
            for entry in feed.entries:
                for link in getattr(entry, "links", []):
                    if getattr(link, "rel", "") == "subsection":
                        candidatos.append(abs_url(BASE_URL, link.href))
                        break
            if len(candidatos) == 1:
                destino_href = candidatos[0]

        # 3) Si hay destino, marca el flag, ajusta título y navega
        if destino_href:
            user_state[uid]["auto_enter_done"] = True
            user_state[uid]["titulo"] = "📁 ZeePubs [ES]"
            user_state[uid]["historial"] = []
            user_state[uid]["libros"] = {}
            user_state[uid]["colecciones"] = {}
            user_state[uid]["nav"] = {"prev": None, "next": None}
            await mostrar_colecciones(update, context, destino_href, from_collection=True)
            return

    # Guardamos esta URL como última página visitada
    user_state[uid]["ultima_pagina"] = url

    if from_collection:
        titulo_actual = user_state[uid].get("titulo", feed.feed.title)
        url_actual = user_state[uid].get("url", root_url)
        user_state[uid]["historial"].append((titulo_actual, url_actual))

    user_state[uid]["url"] = url
    user_state[uid]["libros"] = {}
    user_state[uid]["colecciones"] = {}
    user_state[uid]["nav"] = {"prev": None, "next": None}

    colecciones = []
    libros = []

    # Navegación
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

    # Lista de títulos a ocultar
    ocultar_titulos = {"En el puente","Listas de lectura", "Deseo leer", "Todas las colecciones"}

    # Entradas
    for entry in feed.entries:
        datos_libro = {"titulo": entry.title, "autor": getattr(entry, "author", "Desconocido")}
        # Guardar el link 'self' del entry si existe
        try:
            datos_libro["href"] = entry.link
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
            # Filtrar colecciones no deseadas
            if entry.title.strip() not in ocultar_titulos:
                colecciones.append({"titulo": entry.title, "href": href_sub})
        elif tiene_libro:
            libros.append(datos_libro)

    # Teclado
    keyboard = []
    keyboard.append([InlineKeyboardButton("🔍 Buscar EPUB", callback_data="buscar")])

    if colecciones:
        for idx, col in enumerate(colecciones):
            user_state[uid]["colecciones"][idx] = col
            titulo_normalizado = col["titulo"].strip().lower()
            if titulo_normalizado == "todas las bibliotecas":
                # Si NO estamos en evil, usar el botón especial
                if user_state.get(uid, {}).get("opds_root_base") != OPDS_ROOT_EVIL:
                    keyboard.append([InlineKeyboardButton("📚 Ingresar a Biblioteca", callback_data="abrir_zeepubs")])
                else:
                    # En evil, mostrar la opción original del OPDS
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

    titulo_mostrar = user_state[uid].get("titulo", feed.feed.title)
    reply_markup = InlineKeyboardMarkup(keyboard)
    if getattr(update, "message", None):
        await update.message.reply_text(titulo_mostrar, reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(titulo_mostrar, reply_markup=reply_markup)

async def abrir_zeepubs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id

    # 🔹 Usar el root dinámico del usuario
    root_url = user_state.get(uid, {}).get("opds_root", OPDS_ROOT_START)

    def norm(s: str) -> str:
        return " ".join((s or "").split()).casefold()

    # 1) Intentar encontrar ZeePubs [ES] directamente en el root del usuario
    feed_root = mostrar_feed(root_url)
    destino_href = None

    if feed_root and getattr(feed_root, "entries", []):
        for entry in feed_root.entries:
            if norm(getattr(entry, "title", "")) == norm("ZeePubs [ES]"):
                for link in getattr(entry, "links", []):
                    if getattr(link, "rel", "") == "subsection":
                        destino_href = abs_url(BASE_URL, link.href)
                        break
                if destino_href:
                    break

        # 2) Si no lo encuentra, seguir el enlace de “Todas las bibliotecas” y buscar allí
        if not destino_href:
            biblios_href = None
            for entry in feed_root.entries:
                if norm(getattr(entry, "title", "")) == norm("Todas las bibliotecas"):
                    for link in getattr(entry, "links", []):
                        if getattr(link, "rel", "") == "subsection":
                            biblios_href = abs_url(BASE_URL, link.href)
                            break
                    if biblios_href:
                        break

            if biblios_href:
                feed_biblios = mostrar_feed(biblios_href)
                if feed_biblios and getattr(feed_biblios, "entries", []):
                    for entry in feed_biblios.entries:
                        if norm(getattr(entry, "title", "")) == norm("ZeePubs [ES]"):
                            for link in getattr(entry, "links", []):
                                if getattr(link, "rel", "") == "subsection":
                                    destino_href = abs_url(BASE_URL, link.href)
                                    break
                            if destino_href:
                                break

    # 3) Si logramos resolver destino, entrar como si el usuario hubiese seleccionado la biblioteca
    if destino_href:
        user_state[uid]["titulo"] = "📁 ZeePubs [ES]"
        user_state[uid]["historial"] = []
        user_state[uid]["libros"] = {}
        user_state[uid]["colecciones"] = {}
        user_state[uid]["nav"] = {"prev": None, "next": None}
        await mostrar_colecciones(update, context, destino_href, from_collection=True)
        return

    # 4) Fallback: si algo falla, deja la vista actual sin romper el flujo
    await query.answer("No se pudo abrir la biblioteca directamente. Intenta entrar manualmente.", show_alert=False)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = update.effective_user.id

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
            # Prefiere la URL de descarga (contiene series y volume)
            descarga = str(libro.get("descarga", ""))
            href = str(libro.get("href", ""))  # opcional

            # Intenta extraer series y volume desde la URL de descarga o href
            m = re.search(r'/series/(\d+)/volume/(\d+)/', descarga) or re.search(r'/series/(\d+)/volume/(\d+)/', href)
            if m:
                user_state[uid]["series_id"] = m.group(1)
                user_state[uid]["volume_id"] = m.group(2)
                logging.info(f"DEBUG series_id: {user_state[uid]['series_id']} volume_id: {user_state[uid]['volume_id']}")
            else:
                # Fallback solo series_id si es lo único disponible
                m2 = re.search(r'/series/(\d+)', descarga) or re.search(r'/series/(\d+)', href)
                if m2:
                    user_state[uid]["series_id"] = m2.group(1)
                    logging.info(f"DEBUG series_id: {user_state[uid]['series_id']}")
                else:
                    logging.warning("DEBUG: No se encontraron IDs en URLs del libro")

            user_state[uid]["ultima_pagina"] = href or descarga

            await publicar_libro(uid, libro["titulo"], libro.get("portada", ""), libro.get("descarga", ""))
            await query.edit_message_text(f"✅ Publicado: {libro['titulo']}")

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
        # Borrar mensaje "¿Qué quieres hacer ahora?" si existe
        msg_id = user_state.get(uid, {}).pop("msg_que_hacer", None)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except:
                pass

        # Ir siempre a la raíz base del catálogo actual
        root_base = user_state.get(uid, {}).get("opds_root_base", OPDS_ROOT_START)
        user_state[uid]["opds_root"] = root_base  # actualizar navegación
        await mostrar_colecciones(update, context, root_base, from_collection=False)

    elif data == "volver_ultima":
        # Si hay mensaje "¿Qué quieres hacer ahora?" pendiente, borrarlo
        msg_id = user_state.get(uid, {}).pop("msg_que_hacer", None)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except:
                pass
        # 🔹 Usar root dinámico como valor por defecto
        root_url = user_state.get(uid, {}).get("opds_root", OPDS_ROOT_START)
        ultima_url = user_state[uid].get("ultima_pagina", root_url)
        await mostrar_colecciones(update, context, ultima_url, from_collection=False)

    elif data == "cerrar":
        # Si hay mensaje "¿Qué quieres hacer ahora?" pendiente, borrarlo
        msg_id = user_state.get(uid, {}).pop("msg_que_hacer", None)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except:
                pass
        await query.edit_message_text("👋 ¡Gracias por usar el bot! Hasta la próxima.")

async def volver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if user_state.get(uid, {}).get("historial"):
        titulo_prev, url_prev = user_state[uid]["historial"].pop()
        user_state[uid]["titulo"] = titulo_prev
        await mostrar_colecciones(update, context, url_prev, from_collection=False)
    else:
        await update.message.reply_text("No hay nivel anterior disponible.")

async def publicar_libro(uid, titulo, portada_url, epub_url):
    destino = user_state[uid]["destino"]          # Dónde se publica el contenido
    chat_origen = user_state[uid]["chat_origen"]  # Dónde se envían los menús
    modo = user_state[uid]["modo"]

    # Sinopsis desde OPDS (volumen exacto con fallback a serie)
    series_id = user_state[uid].get("series_id")
    volume_id = user_state[uid].get("volume_id")

    # Guardar la URL actual como última página antes de publicar
    root_url = user_state.get(uid, {}).get("opds_root", OPDS_ROOT_START)
    ultima_url = user_state[uid].get("url", root_url)
    user_state[uid]["ultima_pagina"] = ultima_url

    # --- MODO COMPACTO ---
    if modo == "compacto":
        # Portada sin texto
        if portada_url:
            r = requests.get(portada_url)
            if r.status_code == 200:
                with open("portada.jpg", "wb") as f:
                    f.write(r.content)
                with open("portada.jpg", "rb") as img:
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                        data={"chat_id": destino},
                        files={"photo": img}
                    )
                os.remove("portada.jpg")

        # Aviso temporal
        prep_msg = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": destino, "text": "⏳ Preparando archivo..."}
        ).json()
        prep_msg_id = prep_msg.get("result", {}).get("message_id")

        # Archivo EPUB
        if epub_url:
            r = requests.get(epub_url)
            if r.status_code == 200:
                nombre_archivo = os.path.basename(urlparse(epub_url).path)
                nombre_archivo = unquote(nombre_archivo)
                with open(nombre_archivo, "wb") as f:
                    f.write(r.content)
                with open(nombre_archivo, "rb") as doc:
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
                        data={"chat_id": destino, "caption": titulo},
                        files={"document": (nombre_archivo, doc)}
                    )
                os.remove(nombre_archivo)

        # Borrar aviso temporal
        if prep_msg_id:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage",
                data={"chat_id": destino, "message_id": prep_msg_id}
            )

    # --- MODO CLÁSICO ---
    elif modo == "clasico":
        meta = obtener_metadatos_opds(series_id, volume_id)
        mensaje_portada = formatear_mensaje_portada(meta)

        # Enviar portada con mensaje
        if portada_url:
            r = requests.get(portada_url)
            if r.status_code == 200:
                with open("portada.jpg", "wb") as f:
                    f.write(r.content)
                with open("portada.jpg", "rb") as img:
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                        data={"chat_id": destino, "caption": mensaje_portada},
                        files={"photo": img}
                    )
                os.remove("portada.jpg")

        sinopsis_texto = None
        if series_id and volume_id:
            sinopsis_texto = obtener_sinopsis_opds_volumen(series_id, volume_id)

        if not sinopsis_texto and series_id:
            try:
                sinopsis_texto = obtener_sinopsis_opds(series_id)
            except Exception as e:
                logging.error(f"Error obteniendo sinopsis por serie: {e}")

        if sinopsis_texto:
            sinopsis_esc = html.escape(sinopsis_texto)
            mensaje = f"<b>Sinopsis:</b>\n<blockquote>{sinopsis_esc}</blockquote>"
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": destino, "text": mensaje, "parse_mode": "HTML"}
            )
        else:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": destino, "text": "Sinopsis: (no disponible)"}
            )

        # Aviso temporal
        prep_msg = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": destino, "text": "⏳ Preparando archivo..."}
        ).json()
        prep_msg_id = prep_msg.get("result", {}).get("message_id")

        # EPUB
        if epub_url:
            r = requests.get(epub_url)
            if r.status_code == 200:
                nombre_archivo = os.path.basename(urlparse(epub_url).path)
                nombre_archivo = unquote(nombre_archivo)
                with open(nombre_archivo, "wb") as f:
                    f.write(r.content)
                with open(nombre_archivo, "rb") as doc:
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
                        data={"chat_id": destino, "caption": titulo},
                        files={"document": (nombre_archivo, doc)}
                    )
                os.remove(nombre_archivo)

        # Borrar aviso temporal
        if prep_msg_id:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage",
                data={"chat_id": destino, "message_id": prep_msg_id}
            )

    # --- MENÚ DE OPCIONES ---
    keyboard = [
        [InlineKeyboardButton("📚 Volver a categorías", callback_data="volver_colecciones")],
        [InlineKeyboardButton("↩️ Volver a la página anterior", callback_data="volver_ultima")],
        [InlineKeyboardButton("❌ Cerrar", callback_data="cerrar")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg_temp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": chat_origen, "text": "¿Qué quieres hacer ahora?"}
    ).json()

    msg_temp_id = msg_temp.get("result", {}).get("message_id")
    user_state[uid]["msg_que_hacer"] = msg_temp_id

    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={
            "chat_id": chat_origen,
            "text": "Selecciona una opción:",
            "reply_markup": json.dumps(reply_markup.to_dict())
        }
    )

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Callbacks de botones
    app.add_handler(CallbackQueryHandler(set_destino, pattern="^destino\\|"))
    app.add_handler(CallbackQueryHandler(set_modo, pattern="^modo\\|"))
    app.add_handler(CallbackQueryHandler(buscar_epub, pattern="^buscar$"))
    app.add_handler(CallbackQueryHandler(abrir_zeepubs, pattern="^abrir_zeepubs$"))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("evil", evil))
    app.add_handler(CommandHandler("volver", volver))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Mensajes de texto (destino manual, búsqueda o contraseña de /evil)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_texto))

    # Arranque del bot
    app.run_polling()
