import re
import io
import zipfile
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any


def _parse_opf_bytes(data: bytes) -> Dict[str, Any]:
    """
    Parsea bytes de un .opf y extrae metadatos relevantes.
    Devuelve dict con keys: titulo_volumen, titulo_serie, autores (list),
    ilustrador, generos (list), demografia (list), categoria, maquetadores (list),
    traductor (str), publisher (str), publisher_url (str), sinopsis (str|None).
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
        "sinopsis": None,
    }

    # title
    for el in root.iter():
        lname = local_name(el).lower()
        if lname in ("title", "dc:title") and (el.text or "").strip():
            out["titulo_volumen"] = el.text.strip()
            break

    # belongs-to-collection (series)
    for el in root.iter():
        if local_name(el).lower() == "meta":
            prop = el.attrib.get("property", "") or el.attrib.get("{http://www.idpf.org/2007/opf}property", "")
            if prop == "belongs-to-collection" and el.text:
                out["titulo_serie"] = el.text.strip()
                break

    creators, contributors, id_to_name = [], [], {}
    for el in root.iter():
        lname = local_name(el).lower()
        if lname in ("creator", "dc:creator", "dc_creator"):
            text = (el.text or "").strip()
            if text:
                creators.append(text)
            cid = el.attrib.get("id")
            if cid and text:
                id_to_name[cid] = text
        elif lname in ("contributor", "dc:contributor", "dc_contributor"):
            text = (el.text or "").strip()
            if text:
                contributors.append(text)
            cid = el.attrib.get("id")
            if cid and text:
                id_to_name[cid] = text

    out["autores"] = creators

    subjects = []
    for el in root.iter():
        lname = local_name(el).lower()
        if lname in ("subject", "dc:subject"):
            txt = (el.text or "").strip()
            if txt:
                subjects.append(txt)

    dem_keywords = {"juvenil", "seinen", "shounen", "shoujo", "josei", "kodomomuke", "juvenile", "chicos", "chicos/shounen", "shônen", "shounen"}
    dem, genres = [], []
    for s in subjects:
        sl = s.lower()
        if any(k in sl for k in dem_keywords):
            dem.append(s)
        else:
            genres.append(s)
    out["generos"] = genres
    out["demografia"] = dem

    # description / summary
    for el in root.iter():
        lname = local_name(el).lower()
        if lname in ("description", "dc:description", "summary"):
            txt = (el.text or "").strip()
            if txt:
                out["sinopsis"] = txt
                break

    # type (categoria)
    for el in root.iter():
        lname = local_name(el).lower()
        if lname in ("type", "dc:type"):
            if el.text:
                out["categoria"] = el.text.strip()
                break

    # publisher
    for el in root.iter():
        lname = local_name(el).lower()
        if lname in ("publisher", "dc:publisher", "dc_publisher"):
            if el.text:
                out["publisher"] = el.text.strip()
                break

    # identifier (URL)
    for el in root.iter():
        lname = local_name(el).lower()
        if lname in ("identifier", "dc:identifier", "dc_identifier"):
            txt = (el.text or "").strip()
            if txt and (txt.startswith("http") or txt.startswith("urn:uri:") or txt.startswith("https")):
                if txt.startswith("urn:uri:"):
                    parts = txt.split(":", 2)
                    if len(parts) == 3:
                        txt = parts[-1]
                out["publisher_url"] = txt
                break

    roles = {}  # id -> rolecode
    for el in root.iter():
        if local_name(el).lower() == "meta":
            prop = el.attrib.get("property", "") or el.attrib.get("{http://www.idpf.org/2007/opf}property", "")
            if prop and prop.lower() == "role":
                ref = el.attrib.get("refines", "") or el.attrib.get("{http://www.idpf.org/2007/opf}refines", "")
                if ref and el.text:
                    rid = ref.lstrip('#')
                    roles[rid] = (el.text or "").strip().lower()

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

    if not out["ilustrador"]:
        for name in contributors:
            low = name.lower()
            if any(tok in low for tok in ("ill", "illustrator", "artist", "ilustr")):
                out["ilustrador"] = name
                break
        if not out["ilustrador"] and len(out["autores"]) > 1:
            out["ilustrador"] = out["autores"][-1]

    heur_keywords = ("zeepub", "zeepubs", "saosora", "saosor")
    for name in (list(id_to_name.values()) + contributors):
        low = (name or "").lower()
        if any(k in low for k in heur_keywords):
            if name not in out["maquetadores"]:
                out["maquetadores"].append(name)
    if not out["maquetadores"]:
        for name in contributors:
            if len(name) > 1 and name not in out["maquetadores"]:
                out["maquetadores"].append(name)
        if not out["maquetadores"]:
            for name in id_to_name.values():
                if name not in out["maquetadores"]:
                    out["maquetadores"].append(name)

    # dedupe
    seen, maqs = set(), []
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