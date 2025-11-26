import re
import html
from urllib.parse import urljoin, urlparse
from config.config_settings import config

def get_thread_id(update) -> int:
    """
    Extrae el message_thread_id de un Update de Telegram.
    Retorna None si no hay thread_id (chat privado o grupo sin topics).
    """
    if not update:
        return None
    
    # Intentar desde message
    if hasattr(update, 'message') and update.message:
        return getattr(update.message, 'message_thread_id', None)
    
    # Intentar desde callback_query.message
    if hasattr(update, 'callback_query') and update.callback_query:
        if hasattr(update.callback_query, 'message') and update.callback_query.message:
            return getattr(update.callback_query.message, 'message_thread_id', None)
    
    return None


def is_command_for_bot(update, bot_username: str) -> bool:
    """
    Verifica si un comando está dirigido a este bot específicamente.
    En grupos con múltiples bots, los comandos pueden ir dirigidos a un bot
    específico usando /comando@nombrebot
    
    Args:
        update: Update de Telegram
        bot_username: Username del bot (sin @)
    
    Returns:
        True si el comando es para este bot o no tiene bot específico (chat privado)
        False si el comando es para otro bot
    """
    if not update or not hasattr(update, 'message') or not update.message:
        return True
    
    # En chats privados, siempre es para este bot
    if update.effective_chat.type == 'private':
        return True
    
    # Verificar si el mensaje tiene entidades de comando
    if not update.message.entities:
        return True
    
    # Buscar la entidad de bot_command
    for entity in update.message.entities:
        if entity.type == 'bot_command':
            # Extraer el texto del comando
            command_text = update.message.text[entity.offset:entity.offset + entity.length]
            
            # Si el comando tiene @botusername, verificar que sea este bot
            if '@' in command_text:
                # Formato: /comando@botusername
                mentioned_bot = command_text.split('@')[1]
                return mentioned_bot.lower() == bot_username.lower()
            
            # Si no tiene @, acepta el comando (comportamiento por defecto)
            return True
    
    return True



def abs_url(base: str, href: str) -> str:
    return href if href.startswith("http") else urljoin(base, href)

def norm_string(s: str) -> str:
    return " ".join((s or "").split()).casefold()

def limpiar_html_basico(texto_html: str) -> str:
    if not texto_html:
        return ""
    texto_html = texto_html.replace("<br>", "\n").replace("<br/>", "\n")
    texto_limpio = re.sub(r"<.*?>", "", texto_html)
    return "\n".join([ln.rstrip() for ln in texto_limpio.strip().splitlines() if ln.strip()])

def build_search_url(query: str, uid: int = None) -> str:
    from core.state_manager import state_manager
    root = config.OPDS_ROOT_START
    if uid:
        user_state = state_manager.get_user_state(uid)
        root = user_state.get("opds_root", config.OPDS_ROOT_START)
    if "/series" in root:
        root_series = root.split("?")[0]
    else:
        root_series = f"{root}/series"
    return f"{root_series}?query={query}"

def find_zeepubs_destino(feed, prefer_libraries: bool = False):
    import logging
    from urllib.parse import urlparse
    if not feed:
        logging.debug("find_zeepubs_destino: feed is None")
        return None
    entries = getattr(feed, "entries", [])
    logging.debug("find_zeepubs_destino: feed title=%s entries=%d", getattr(feed, "feed", {}).get("title", None), len(entries))
    def norm(s): return " ".join((s or "").split()).casefold()
    candidatos = []
    for entry in entries:
        title = getattr(entry, "title", "")
        logging.debug("find_zeepubs_destino: entry.title=%r", title)
        tnorm = norm(title)
        for link in getattr(entry, "links", []):
            rel = getattr(link, "rel", "")
            href = getattr(link, "href", "")
            logging.debug(" find link rel=%r href=%r (entry=%r)", rel, href, title)
            if rel == "subsection" and href:
                full = abs_url(config.BASE_URL, href)
                candidatos.append((title, full))
                if "zeepub" in tnorm or "zeepubs" in tnorm or tnorm == norm("ZeePubs [ES]"):
                    logging.debug("find_zeepubs_destino: título coincide con 'zeepub(s)': %r -> %s", title, full)
                    return full
    if prefer_libraries:
        for title, href in candidatos:
            path = urlparse(href).path.lower()
            if "/libraries" in path or "/collections" in path or "/library" in path:
                logging.debug("find_zeepubs_destino: (prefer_libraries) href contains pattern, choosing %s (title=%r)", href, title)
                return href
        for title, href in candidatos:
            if "bibliotec" in norm(title):
                logging.debug("find_zeepubs_destino: (prefer_libraries) title suggests 'biblioteca', choosing %s (title=%r)", href, title)
                return href
    if len(candidatos) == 1:
        logging.debug("find_zeepubs_destino: unique candidate, returning %s", candidatos[0][1])
        return candidatos[0][1]
    logging.debug("find_zeepubs_destino: no destination found (candidates=%s)", [c for _, c in candidatos])
    return None

def generar_slug_from_meta(meta: dict) -> str:
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
    for ch in ("'", "’", "#", "・"):
        base_titulo = base_titulo.replace(ch, "")
    base_titulo = re.sub(r"\s+", " ", base_titulo).strip()
    slug = base_titulo.replace(" ", "_")
    return slug

def parse_title_string(title_str: str) -> tuple[str, str]:
    """
    Parsea un título completo (ej: "Serie - Volumen 01 [Tag]")
    Retorna (titulo_serie, volumen).
    """
    if not title_str:
        return "", ""
        
    # Regex para encontrar "Volumen XX"
    vol_match = re.search(r'(Volumen\s+\d+(\.\d+)?)', title_str, re.IGNORECASE)
    volume = vol_match.group(1) if vol_match else ""
    
    # Serie: Todo antes de " - Volumen" o eliminar volumen y tags
    series = title_str
    if " - " in title_str:
        parts = title_str.split(" - ")
        # Asumimos que la primera parte es la serie si hay separador claro
        series = parts[0].strip()
    else:
        # Fallback: eliminar volumen y tags
        if volume:
            series = series.replace(volume, "")
        series = re.sub(r'\[.*?\]', '', series).strip()
        
    return series.strip(), volume.strip()

def formatear_mensaje_portada(meta: dict) -> str:
    slug = generar_slug_from_meta(meta)
    lines = []
    
    # Nueva lógica si existen los campos específicos
    internal_title = meta.get("internal_title")
    collection_title = meta.get("titulo_serie")
    
    # Limpiar collection_title: remover [...] y su contenido
    if collection_title:
        collection_title = re.sub(r'\[.*?\]', '', collection_title).strip()
    
    if internal_title and collection_title:
        full_title = meta.get("titulo_volumen") or ""
        series, volume = parse_title_string(full_title)
        
        # Si no se encontró volumen, usar el título completo como serie (o dejar vacío volumen)
        if not series:
            series = full_title
            
        lines.extend([
            f"Epub de: {series} ║ {collection_title} ║ {internal_title}",
            volume,
            f"#{slug}" if slug else ""
        ])
    else:
        # Lógica antigua (fallback)
        titulo_vol = meta.get("titulo_volumen") or ""
        lines.extend([
            titulo_vol,
            f"#{slug}" if slug else ""
        ])

    # Common metadata fields
    categoria = meta.get("categoria") or "Desconocida"
    generos = ", ".join(meta.get("generos") or []) or "Desconocido"
    demografia = ", ".join(meta.get("demografia") or []) or "Desconocida"
    autor = meta.get("autor") or (meta.get("autores")[0] if meta.get("autores") else "Desconocido")
    ilustrador = meta.get("ilustrador") or "Desconocido"
    maqus = meta.get("maquetadores") or []
    if not maqus:
        maqu_line = "<b>Maquetado por:</b> #ZeePub"
    else:
        maqu_line = "<b>Maquetado por:</b> " + " ".join(f"#{m.replace(' ', '')}" for m in maqus)
    
    traduccion_parts = []
    if meta.get("traductor"):
        traduccion_parts.append(meta["traductor"])
    if meta.get("publisher"):
        traduccion_parts.append(meta["publisher"])
    if meta.get("publisher_url"):
        traduccion_parts.append(meta["publisher_url"])
    traduccion_line = ""
    if traduccion_parts:
        traduccion_line = "<b>Traducción:</b> " + " − ".join(traduccion_parts)

    lines.append("") # Empty line separator
    lines.extend([
        maqu_line,
        f"<b>Categoría:</b> {categoria}",
        f"<b>Demografía:</b> {demografia}",
        f"<b>Géneros:</b> {generos}",
        f"<b>Autor:</b> {autor}",
        f"<b>Ilustrador:</b> {ilustrador}",
    ])

    if meta.get("fecha_publicacion"):
        lines.append(f"<b>Publicado:</b> {meta['fecha_publicacion']}")
    if traduccion_line:
        lines.append(traduccion_line)

    # Filter out None but keep empty strings (though lines shouldn't have None)
    return "\n".join(line for line in lines if line is not None)

def escapar_html(texto: str) -> str:
    return html.escape(texto) if texto else ""
