"""Modern Office formats — .docx / .xlsx / .pptx — read directly from their
OOXML (zip + XML) with only the standard library.

OOXML files are zip containers of XML. Word text lives in <w:t>, PowerPoint in
<a:t>, Excel cells reference an <si> shared-strings table. We match by XML
local-name so namespace prefixes never matter.
"""

import zipfile
from xml.etree import ElementTree as ET

from ..document import Document
from .base import Backend, Options


def _ln(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _docx(path: str):
    pieces = []
    with zipfile.ZipFile(path) as z:
        parts = [n for n in z.namelist()
                 if n == "word/document.xml"
                 or (n.startswith("word/header") and n.endswith(".xml"))
                 or (n.startswith("word/footer") and n.endswith(".xml"))
                 or n.startswith("word/footnotes") or n.startswith("word/endnotes")]
        parts.sort(key=lambda n: (n != "word/document.xml", n))
        for part in parts:
            try:
                root = ET.fromstring(z.read(part))
            except (ET.ParseError, KeyError):
                continue
            for p in root.iter():
                if _ln(p.tag) != "p":
                    continue
                buf = []
                for node in p.iter():
                    ln = _ln(node.tag)
                    if ln == "t" and node.text:
                        buf.append(node.text)
                    elif ln == "tab":
                        buf.append("\t")
                    elif ln in ("br", "cr"):
                        buf.append("\n")
                pieces.append("".join(buf))
    return [("document", "\n".join(pieces))]


def _pptx(path: str):
    slides = []
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist()
                       if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
        for i, n in enumerate(names, 1):
            try:
                root = ET.fromstring(z.read(n))
            except ET.ParseError:
                continue
            lines, cur = [], []
            for node in root.iter():
                ln = _ln(node.tag)
                if ln == "t" and node.text:
                    cur.append(node.text)
                elif ln == "p":              # drawingML paragraph boundary
                    if cur:
                        lines.append("".join(cur))
                        cur = []
            if cur:
                lines.append("".join(cur))
            slides.append((f"slide {i}", "\n".join(lines)))
    return slides


def _xlsx(path: str):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            try:
                root = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in root:
                    if _ln(si.tag) == "si":
                        shared.append("".join(t.text or "" for t in si.iter()
                                              if _ln(t.tag) == "t"))
            except ET.ParseError:
                pass
        sheets = sorted(n for n in names
                        if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        out = []
        for i, n in enumerate(sheets, 1):
            try:
                root = ET.fromstring(z.read(n))
            except ET.ParseError:
                continue
            rows = []
            for row in root.iter():
                if _ln(row.tag) != "row":
                    continue
                cells = []
                for c in row:
                    if _ln(c.tag) != "c":
                        continue
                    ctype = c.get("t")
                    val = None
                    for child in c:
                        ln = _ln(child.tag)
                        if ln == "v":
                            val = child.text
                        elif ln == "is":
                            val = "".join(x.text or "" for x in child.iter()
                                          if _ln(x.tag) == "t")
                    if val is None:
                        continue
                    if ctype == "s":
                        try:
                            val = shared[int(val)]
                        except (ValueError, IndexError):
                            pass
                    cells.append(str(val))
                if cells:
                    rows.append("\t".join(cells))
            out.append((f"sheet {i}", "\n".join(rows)))
        return out


class OfficeBackend(Backend):
    name = "office"
    kinds = ("docx", "xlsx", "pptx")

    _READERS = {"docx": _docx, "xlsx": _xlsx, "pptx": _pptx}

    def extract(self, path: str, kind: str, opts: Options) -> Document:
        doc = Document(path=path, kind=kind, backend=self.name)
        try:
            sections = self._READERS[kind](path)
        except (zipfile.BadZipFile, KeyError) as exc:
            return Document.failed(path, f"not a valid {kind}: {exc}", kind)
        for label, text in sections:
            doc.add_page(text, method=f"{kind}-xml", label=label)
        return doc
