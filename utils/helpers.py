import re
import logging
from urllib.parse import urljoin, urlparse
from config.config_settings import config
from core.state_manager import state_manager

logger = logging.getLogger(__name__)

def abs_url(base, href):
    """Convert relative URL to absolute URL"""
    return href if href.startswith("http") else urljoin(base, href)

def norm_string(s: str) -> str:
    """Normalize string: collapse spaces and convert to lowercase"""
    return " ".join((s or "").split()).casefold()

def limpiar_html_basico(texto_html: str) -> str:
    """
    Convert <br/> to line breaks, remove other HTML tags,
    and clean redundant empty lines.
    """
    if not texto_html:
        return ""

    texto_html = texto_html.replace("<br/>", "\n").replace("<br>", "\n")
    texto_limpio = re.sub(r"<.*?>", "", texto_html)
    return "\n".join([ln.rstrip() for ln in texto_limpio.strip().splitlines() if ln.strip()])

def build_search_url(query: str, uid: int | None = None) -> str:
    """
    Build search URL using user's current OPDS root (if exists).
    """
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
    """
    Given a feedparser.FeedParserDict, try to locate ZeePubs subsection.
    - If prefer_libraries=True, prioritizes links with /libraries or /collections
    - If prefer_libraries=False, uses conservative heuristic: search for 'zeepub(s)' in title or
      return unique subsection candidate if only one exists
    Returns absolute href or None.
    """
    if not feed:
        logger.debug("find_zeepubs_destino: feed is None")
        return None

    entries = getattr(feed, "entries", [])
    logger.debug(f"find_zeepubs_destino: feed title={getattr(feed, 'feed', {}).get('title', None)} entries={len(entries)}")

    def norm(s):
        return " ".join((s or "").split()).casefold()

    candidatos = []  # (title, href)
    for entry in entries:
        title = getattr(entry, "title", "")
        logger.debug(f"find_zeepubs_destino: entry.title={title!r}")
        tnorm = norm(title)

        for link in getattr(entry, "links", []):
            rel = getattr(link, "rel", "")
            href = getattr(link, "href", "")
            logger.debug(f" find link rel={rel!r} href={href!r} (entry={title!r})")

            if rel == "subsection" and href:
                full_url = abs_url(config.BASE_URL, href)
                candidatos.append((title, full_url))

                # Explicit 'zeepub' match in title -> immediate return
                if "zeepub" in tnorm or "zeepubs" in tnorm or tnorm == norm("ZeePubs [ES]"):
                    logger.debug(f"find_zeepubs_destino: título coincide con 'zeepub(s)': {title!r} -> {full_url}")
                    return full_url

    if prefer_libraries:
        for title, href in candidatos:
            path = urlparse(href).path.lower()
            if "/libraries" in path or "/collections" in path or "/library" in path:
                logger.debug(f"find_zeepubs_destino: (prefer_libraries) href contiene patrón de biblioteca, eligiendo {href} (title={title!r})")
                return href

        for title, href in candidatos:
            if "bibliotec" in norm(title):
                logger.debug(f"find_zeepubs_destino: (prefer_libraries) título sugiere 'biblioteca', eligiendo {href} (title={title!r})")
                return href

    if len(candidatos) == 1:
        logger.debug(f"find_zeepubs_destino: único candidato disponible, devolviendo {candidatos[0][1]}")
        return candidatos[0][1]

    logger.debug(f"find_zeepubs_destino: no se encontró destino (candidatos={[c for _, c in candidatos]})")
    return None

def generar_slug_from_meta(meta: dict) -> str:
    """
    Generate a slug based on meta['titulo_serie'] if exists.
    If no series title, try titulo_volumen then empty.
    Normalizes by removing brackets, hyphens, commas, apostrophes and requested symbols,
    and replaces spaces with underscores.
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

    for ch in ("'", "'", "#", "・"):
        base_titulo = base_titulo.replace(ch, "")

    base_titulo = re.sub(r"\s+", " ", base_titulo).strip()
    slug = base_titulo.replace(" ", "_")
    return slug

def formatear_mensaje_portada(meta: dict) -> str:
    """
    Format cover message with metadata
    """
    slug = generar_slug_from_meta(meta)

    titulo_serie = meta.get("titulo_serie")
    if titulo_serie:
        base_titulo = titulo_serie.split(":", 1)[0].strip()
        base_titulo = re.sub(r"\[.*?\]", "", base_titulo)
        base_titulo = base_titulo.split("-", 1)[0].strip()
        base_titulo = base_titulo.replace(",", " ")
        for ch in ("'", "'", "#", "・"):
            base_titulo = base_titulo.replace(ch, "")
        # The slug we already have in 'slug'
    else:
        slug = slug or ""

    categoria = meta.get("categoria") or "Desconocida"
    generos_list = meta.get("generos") or []
    generos = ", ".join(generos_list) if generos_list else "Desconocido"
    demografia_list = meta.get("demografia") or []
    demografia = ", ".join(demografia_list) if demografia_list else "Desconocida"
    autor = meta.get("autor") or (meta.get("autores")[0] if meta.get("autores") else "Desconocido")
    ilustrador = meta.get("ilustrador") or "Desconocido"

    maqus = meta.get("maquetadores") or []
    if not maqus:
        maqu_line = "Maquetado por: #ZeePub"
    else:
        maqu_line = "Maquetado por: " + " ".join(f"#{m.replace(' ', '')}" for m in maqus)

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

    lines = [l for l in lines if l is not None]
    return "\n".join(lines)
