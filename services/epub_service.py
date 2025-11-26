# services/epub_service.py

import io
import os
import zipfile
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, Union
from utils.helpers import limpiar_html_basico
import re

def extract_internal_title(data_or_path: Union[bytes, str]) -> Optional[str]:
    """
    Busca un título interno en archivos 'title' o 'titulo' dentro del EPUB.
    Prioriza <... epub:type="fulltitle"> y combina title/subtitle.
    Fallback a <span class="grande" epub:type="title">.
    """
    try:
        if isinstance(data_or_path, (bytes, bytearray)):
            zf = zipfile.ZipFile(io.BytesIO(data_or_path))
        else:
            zf = zipfile.ZipFile(data_or_path)
        
        # Buscar archivos candidatos
        candidates = [n for n in zf.namelist() if "title" in n.lower() or "titulo" in n.lower()]
        
        # Regex para fulltitle: <tag ... epub:type="fulltitle" ...> content </tag>
        fulltitle_pattern = re.compile(r'<(\w+)[^>]*epub:type="fulltitle"[^>]*>(.*?)</\1>', re.IGNORECASE | re.DOTALL)
        
        # Regex para componentes internos
        title_pat = re.compile(r'epub:type="title"[^>]*>(.*?)<', re.IGNORECASE | re.DOTALL)
        subtitle_pat = re.compile(r'epub:type="subtitle"[^>]*>(.*?)<', re.IGNORECASE | re.DOTALL)

        # Regex legacy/fallback
        pattern_legacy = re.compile(r'<span[^>]*class="grande"[^>]*epub:type="title"[^>]*>(.*?)</span>', re.IGNORECASE | re.DOTALL)
        pattern_loose = re.compile(r'<span[^>]*epub:type="title"[^>]*>(.*?)</span>', re.IGNORECASE | re.DOTALL)

        for name in candidates:
            try:
                content = zf.read(name).decode("utf-8", errors="ignore")
                
                # 1. Intentar fulltitle
                match = fulltitle_pattern.search(content)
                if match:
                    inner_html = match.group(2)
                    
                    # Buscar title y subtitle dentro
                    t_match = title_pat.search(inner_html)
                    s_match = subtitle_pat.search(inner_html)
                    
                    if t_match and s_match:
                        t_text = re.sub(r'<[^>]+>', '', t_match.group(1)).strip()
                        s_text = re.sub(r'<[^>]+>', '', s_match.group(1)).strip()
                        
                        if t_text and s_text:
                            # Agregar separador si no existe
                            if not t_text.endswith(':') and not t_text.endswith('-'):
                                return f"{t_text}: {s_text}"
                            return f"{t_text} {s_text}"
                    
                    # Si no hay sub-tags claros, limpiar HTML (reemplazando br con espacio)
                    clean = re.sub(r'<br\s*/?>', ' ', inner_html, flags=re.IGNORECASE)
                    clean = re.sub(r'<[^>]+>', '', clean).strip()
                    if clean:
                        return clean

                # 2. Fallback a lógica anterior
                match = pattern_legacy.search(content)
                if not match:
                    match = pattern_loose.search(content)
                
                if match:
                    text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                    return text
            except Exception:
                continue
                
        return None
    except Exception:
        return None

async def parse_opf_from_epub(data_or_path: Union[bytes, str]) -> Dict[str, Any]:
    """
    Extrae metadatos OPF de un EPUB (bytes o ruta) usando namespaces y heurísticas.
    Retorna dict con claves:
      titulo_volumen, titulo_serie, autores (list), ilustrador, generos (list),
      demografia (list), categoria, maquetadores (list), traductor, publisher,
      publisher_url, sinopsis.
    """
    def _read_opf(z: zipfile.ZipFile) -> Optional[bytes]:
        # Leer container.xml para ubicar el .opf
        try:
            container = z.read("META-INF/container.xml")
            tree = ET.fromstring(container)
            for rf in tree.findall(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"):
                path = rf.attrib.get("full-path", "")
                if path.lower().endswith(".opf"):
                    return z.read(path)
        except Exception:
            pass
        # Fallback: primer .opf en el zip
        for name in z.namelist():
            if name.lower().endswith(".opf"):
                return z.read(name)
        return None

    def local_name(elem: ET.Element) -> str:
        tag = elem.tag
        return tag.split("}", 1)[-1] if "}" in tag else tag

    def local_name_attr(attr_name: str) -> str:
        return attr_name.split("}", 1)[-1] if "}" in attr_name else attr_name

    def parse_date(raw_date: str) -> str:
        try:
            if "T" in raw_date:
                dt_str = raw_date.split("T")[0]
                parts = dt_str.split("-")
                if len(parts) == 3:
                    return f"{parts[2]}-{parts[1]}-{parts[0]}"
            else:
                parts = raw_date.split("-")
                if len(parts) == 3:
                    return f"{parts[2]}-{parts[1]}-{parts[0]}"
        except Exception:
            pass
        return raw_date

    def _parse_opf(data: bytes) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        
        root = ET.fromstring(data)
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
            "sinopsis": None,
            "epub_version": None,
            "fecha_modificacion": None,
            "fecha_publicacion": None,
        }

        # Version EPUB: <package version="...">
        # root es el elemento <package>
        version = root.attrib.get("version")
        out["epub_version"] = version
        logger.debug(f"EPUB version extracted: {version}")

        # Fecha modificación: dcterms:modified
        # Ejemplo: <meta property="dcterms:modified">2022-07-03T10:28:12Z</meta>
        for el in root.iter():
            ln = local_name(el).lower()
            if ln == "meta":
                # Obtener atributos property y name ignorando namespaces
                attribs = {local_name_attr(k).lower(): v for k, v in el.attrib.items()}
                prop = attribs.get("property", "")
                name = attribs.get("name", "")
                
                if "modified" in prop or "modified" in name:
                    if el.text:
                        raw_date = el.text.strip()
                        out["fecha_modificacion"] = parse_date(raw_date)
                        logger.debug(f"Modified date found: {raw_date} -> {out['fecha_modificacion']}")
                        break

        # Fecha publicación: dc:date
        # Ejemplo: <dc:date>2020-07-02T00:00:00Z</dc:date>
        for el in root.iter():
            ln = local_name(el).lower()
            if ln == "date":
                # Verificar si es dc:date (aunque local_name ya lo filtra, aseguramos que sea fecha)
                if el.text:
                    raw_date = el.text.strip()
                    # Si ya tenemos una fecha, solo sobrescribimos si el evento es 'publication'
                    attribs = {local_name_attr(k).lower(): v for k, v in el.attrib.items()}
                    event = attribs.get("event", "")
                    
                    parsed = parse_date(raw_date)
                    if not out["fecha_publicacion"]:
                        out["fecha_publicacion"] = parsed
                        logger.debug(f"Publication date found: {raw_date} -> {parsed}")
                    elif event == "publication":
                        out["fecha_publicacion"] = parsed
                        logger.debug(f"Publication date (event=publication) found: {raw_date} -> {parsed}")
                        break

        # Título volumen: primer <dc:title> o <title>
        for el in root.iter():
            if local_name(el).lower() == "title" and el.text:
                out["titulo_volumen"] = el.text.strip()
                break

        # Título serie: <meta property="belongs-to-collection">
        for el in root.iter():
            if local_name(el).lower() == "meta":
                prop = el.attrib.get("property", "") or el.attrib.get("{http://www.idpf.org/2007/opf}property", "")
                if prop == "belongs-to-collection" and el.text:
                    out["titulo_serie"] = el.text.strip()
                    break

        # Creators & contributors
        contributors = []
        id_to_name: Dict[str, str] = {}
        for el in root.iter():
            ln = local_name(el).lower()
            if ln in ("creator", "dc:creator"):
                text = (el.text or "").strip()
                if text:
                    out["autores"].append(text)
                cid = el.attrib.get("id")
                if cid and text:
                    id_to_name[cid] = text
            elif ln in ("contributor", "dc:contributor"):
                text = (el.text or "").strip()
                if text:
                    contributors.append(text)
                cid = el.attrib.get("id")
                if cid and text:
                    id_to_name[cid] = text

        # Subjects => géneros y demografía
        subjects = [ (el.text or "").strip() for el in root.iter() if local_name(el).lower() in ("subject","dc:subject") and el.text ]
        dem_keys = {"seinen","shounen","shônen","shoujo","josei","juvenil"}
        for s in subjects:
            if any(k in s.lower() for k in dem_keys):
                out["demografia"].append(s)
            else:
                out["generos"].append(s)

        # Sinopsis: dc:description, description o summary
        for el in root.iter():
            ln = local_name(el).lower()
            if ln in ("description","dc:description","summary") and el.text:
                out["sinopsis"] = limpiar_html_basico(el.text.strip())
                break

        # Categoría: dc:type
        for el in root.iter():
            if local_name(el).lower() in ("type","dc:type") and el.text:
                out["categoria"] = el.text.strip()
                break

        # Publisher
        for el in root.iter():
            if local_name(el).lower() in ("publisher","dc:publisher") and el.text:
                out["publisher"] = el.text.strip()
                break

        # Publisher URL: dc:identifier con http o urn:uri
        for el in root.iter():
            if local_name(el).lower() in ("identifier","dc:identifier") and el.text:
                txt = el.text.strip()
                if txt.startswith("http") or txt.startswith("urn:uri:"):
                    if txt.startswith("urn:uri:"):
                        parts = txt.split(":",2)
                        txt = parts[-1] if len(parts)==3 else txt
                    out["publisher_url"] = txt
                    break

        # Roles meta: map id->role
        roles: Dict[str,str] = {}
        for el in root.iter():
            if local_name(el).lower()=="meta":
                prop = el.attrib.get("property","") or el.attrib.get("{http://www.idpf.org/2007/opf}property","")
                if prop.lower()=="role":
                    ref = el.attrib.get("refines","") or el.attrib.get("{http://www.idpf.org/2007/opf}refines","")
                    if ref and el.text:
                        roles[ref.lstrip("#")] = el.text.strip().lower()

        # Asignar roles
        maquet_roles = {"mrk","dst","mqt","mkr"}
        for rid, role in roles.items():
            name = id_to_name.get(rid)
            if not name:
                continue
            if role in maquet_roles:
                out["maquetadores"].append(name)
            elif role in ("trl","translator"):
                out["traductor"] = name
            elif role in ("ill","illustrator","artist"):
                out["ilustrador"] = name
            elif role in ("aut","author") and not out["autores"]:
                out["autores"].append(name)

        # Heurísticas si falta ilustrador o maquetadores
        if not out["ilustrador"]:
            for c in contributors:
                if any(tok in c.lower() for tok in ("ill","artist")):
                    out["ilustrador"] = c; break
        if not out["maquetadores"]:
            for c in contributors:
                if any(tok in c.lower() for tok in ("saosora","zeepub")):
                    out["maquetadores"].append(c)
            if not out["maquetadores"]:
                out["maquetadores"].extend(contributors)

        # Dedupe maquetadores
        seen=set(); mq=[]
        for m in out["maquetadores"]:
            if m not in seen:
                seen.add(m); mq.append(m)
        out["maquetadores"]=mq

        return out

    try:
        # Abrir EPUB
        if isinstance(data_or_path, (bytes, bytearray)):
            zf = zipfile.ZipFile(io.BytesIO(data_or_path))
        else:
            zf = zipfile.ZipFile(data_or_path)
        opf_data = _read_opf(zf)
        if not opf_data:
            return None
        return _parse_opf(opf_data)
    except Exception:
        return None

def extract_cover_from_epub(data_or_path: Union[bytes, str]) -> Optional[bytes]:
    """
    Extrae y devuelve los bytes de la portada embebida en el EPUB,
    buscando primero <meta property="cover"> y luego cualquier
    image/* con 'cover' en id o href. Retorna None si no la halla.
    """
    try:
        if isinstance(data_or_path, (bytes, bytearray)):
            zf = zipfile.ZipFile(io.BytesIO(data_or_path))
        else:
            zf = zipfile.ZipFile(data_or_path)
        namelist = zf.namelist()
        lower_map = {n.lower(): n for n in namelist}

        # 1) localizar OPF
        try:
            container = zf.read("META-INF/container.xml")
            tree = ET.fromstring(container)
            opf_path = next(
                rf.attrib["full-path"]
                for rf in tree.findall(
                    ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
                )
                if rf.attrib.get("full-path","").lower().endswith(".opf")
            )
        except StopIteration:
            opf_path = next(name for name in namelist if name.lower().endswith(".opf"))
        real_opf = lower_map.get(opf_path.lower(), opf_path)

        # 2) leer OPF
        opf_data = zf.read(real_opf)
        root = ET.fromstring(opf_data)
        ns = {"opf":"http://www.idpf.org/2007/opf"}

        # 3) meta cover id
        cover_id = None
        for m in root.findall(".//opf:meta", ns):
            if m.attrib.get("property","").lower()=="cover":
                cover_id = m.attrib.get("content")
                break

        # 4) manifest lookup
        manifest = root.findall(".//opf:item", ns)
        target_href = None
        if cover_id:
            for item in manifest:
                if item.attrib.get("id")==cover_id:
                    target_href = item.attrib.get("href")
                    break
        if not target_href:
            for item in manifest:
                href = item.attrib.get("href","").lower()
                iid = item.attrib.get("id","").lower()
                mt = item.attrib.get("media-type","")
                if mt.startswith("image/") and "cover" in (iid+href):
                    target_href = item.attrib.get("href")
                    break

        if not target_href:
            return None

        # 5) leer bytes portada
        base = os.path.dirname(real_opf)
        full = f"{base}/{target_href}".lstrip("/")
        real_cover = lower_map.get(full.lower(), full)
        return zf.read(real_cover)
    except Exception:
        return None