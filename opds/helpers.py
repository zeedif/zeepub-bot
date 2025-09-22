import logging
from urllib.parse import urljoin, urlparse
from config import BASE_URL

def abs_url(base: str, href: str) -> str:
    return href if href.startswith("http") else urljoin(base, href)

def norm_string(s: str) -> str:
    return " ".join((s or "").split()).casefold()

def mostrar_feed(url, feedparser):
    feed = feedparser.parse(url)
    return None if feed.bozo else feed

def find_zeepubs_destino(feed, prefer_libraries: bool = False):
    """
    Busca subsección de ZeePubs en un feed OPDS.
    """
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
                full = abs_url(BASE_URL, href)
                candidatos.append((title, full))
                if "zeepub" in tnorm or "zeepubs" in tnorm or tnorm == norm("ZeePubs [ES]"):
                    logging.debug("find_zeepubs_destino: título coincide con 'zeepub(s)': %r -> %s", title, full)
                    return full

    if prefer_libraries:
        for title, href in candidatos:
            path = urlparse(href).path.lower()
            if "/libraries" in path or "/collections" in path or "/library" in path:
                logging.debug("find_zeepubs_destino: (prefer_libraries) href contiene patrón de biblioteca, eligiendo %s (title=%r)", href, title)
                return href
        for title, href in candidatos:
            if "bibliotec" in norm(title):
                logging.debug("find_zeepubs_destino: (prefer_libraries) título sugiere 'biblioteca', eligiendo %s (title=%r)", href, title)
                return href

    if len(candidatos) == 1:
        logging.debug("find_zeepubs_destino: único candidato disponible, devolviendo %s", candidatos[0][1])
        return candidatos[0][1]

    logging.debug("find_zeepubs_destino: no se encontró destino (candidatos=%s)", [c for _, c in candidatos])
    return None