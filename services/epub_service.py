# services/epub_service.py

import io
import zipfile
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any
from utils.helpers import limpiar_html_basico

async def parse_opf_from_epub(data_or_path) -> Optional[Dict[str, Any]]:
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

    def _parse_opf(data: bytes) -> Dict[str, Any]:
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
        }

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
