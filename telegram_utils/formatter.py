import re
import html


def norm_string(s: str) -> str:
    return " ".join((s or "").split()).casefold()


def limpiar_html_basico(texto_html: str) -> str:
    """
    Convierte <br/> en saltos de línea, elimina etiquetas HTML básicas,
    y limpia líneas vacías redundantes.
    """
    if not texto_html:
        return ""
    texto_html = texto_html.replace("<br/>", "\n").replace("<br>", "\n")
    texto_limpio = re.sub(r"<.*?>", "", texto_html)
    return "\n".join([ln.rstrip() for ln in texto_limpio.strip().splitlines() if ln.strip()])


def generar_slug_from_meta(meta: dict) -> str:
    """
    Genera un slug basado en meta['titulo_serie'] si existe, luego 'titulo_volumen'.
    Normaliza y reemplaza espacios por guiones bajos.
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
    for ch in ("'", "’", "#", "・"):
        base_titulo = base_titulo.replace(ch, "")
    base_titulo = re.sub(r"\s+", " ", base_titulo).strip()
    slug = base_titulo.replace(" ", "_")
    return slug


def formatear_mensaje_portada(meta: dict) -> str:
    slug = generar_slug_from_meta(meta)

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
    traduccion_line = "Traducción: " + " − ".join(traduccion_parts) if traduccion_parts else ""

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

    # quitar None y unir
    lines = [l for l in lines if l is not None]
    return "\n".join(lines)


def escapar_html(texto: str) -> str:
    try:
        return html.escape(texto)
    except Exception:
        return texto