import re
import html
from urllib.parse import urljoin, urlparse
from config.config_settings import config

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

def formatear_mensaje_portada(meta: dict) -> str:
    slug = generar_slug_from_meta(meta)
    titulo_vol = meta.get("titulo_volumen") or ""
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
    lines = [
        titulo_vol,
        f"#{slug}" if slug else "",
        "",  # línea en blanco garantizada
        maqu_line,
        f"<b>Categoría:</b> {categoria}",
        f"<b>Demografía:</b> {demografia}",
        f"<b>Géneros:</b> {generos}",
        f"<b>Autor:</b> {autor}",
        f"<b>Ilustrador:</b> {ilustrador}",
    ]
    if meta.get("fecha_publicacion"):
        lines.append(f"<b>Publicado:</b> {meta['fecha_publicacion']}")
    if traduccion_line:
        lines.append(traduccion_line)
    # No filtramos cadenas vacías para preservar los saltos de línea
    return "\n".join(lines)

def escapar_html(texto: str) -> str:
    return html.escape(texto) if texto else ""
