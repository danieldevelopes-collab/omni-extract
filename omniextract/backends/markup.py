"""HTML / XML / XHTML → visible text, using only the standard library.

A small HTMLParser subclass that drops <script>/<style>, inserts newlines on
block boundaries, and unescapes entities. Good enough to recover the readable
text of a page without pulling in BeautifulSoup/lxml.
"""

from html.parser import HTMLParser

from ..document import Document
from .base import Backend, Options
from .plaintext import _decode

_SKIP = {"script", "style", "head", "noscript", "template"}
_BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
          "section", "article", "header", "footer", "table", "ul", "ol",
          "blockquote", "pre", "hr"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP and self._skip:
            self._skip -= 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data)

    def text(self):
        return "".join(self.parts)


class MarkupBackend(Backend):
    name = "markup"
    kinds = ("html", "xml")

    def extract(self, path: str, kind: str, opts: Options) -> Document:
        doc = Document(path=path, kind=kind, backend=self.name)
        with open(path, "rb") as fh:
            data = fh.read()
        doc.bytes_in = len(data)
        raw, enc, warns = _decode(data)
        doc.meta["encoding"] = enc
        doc.warnings += warns
        if kind == "xml":
            # For generic XML, strip tags but keep all text nodes.
            parser = _Text()
            try:
                parser.feed(raw)
            except Exception as exc:
                doc.warnings.append(f"xml parse: {exc}")
            doc.text = parser.text()
            doc.meta["mode"] = "xml-textnodes"
        else:
            parser = _Text()
            try:
                parser.feed(raw)
            except Exception as exc:
                doc.warnings.append(f"html parse: {exc}")
            doc.text = parser.text()
        doc.add_page(doc.text, method="markup-strip")
        return doc
