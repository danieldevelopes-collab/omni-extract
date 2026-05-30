"""E-books. EPUB is a zip of XHTML chapters — handled with the stdlib. Other
formats (mobi, fb2, cbz, xps) are delegated to PyMuPDF when it's installed.
"""

import zipfile

from ..document import Document
from .base import Backend, Options, _try_import
from .markup import _Text


def _epub_chapters(path: str):
    chapters = []
    with zipfile.ZipFile(path) as z:
        # Prefer reading-order from the OPF spine; fall back to sorted names.
        html_names = [n for n in z.namelist()
                      if n.lower().endswith((".xhtml", ".html", ".htm"))]
        html_names.sort()
        for n in html_names:
            try:
                raw = z.read(n).decode("utf-8", "replace")
            except KeyError:
                continue
            parser = _Text()
            try:
                parser.feed(raw)
            except Exception:
                continue
            txt = parser.text().strip()
            if txt:
                chapters.append((n.rsplit("/", 1)[-1], txt))
    return chapters


class EbookBackend(Backend):
    name = "ebook"
    kinds = ("epub", "ebook")

    def available(self):
        # epub always works (stdlib); other ebook kinds need PyMuPDF.
        return True, "(non-epub e-books need: pip install PyMuPDF)"

    def extract(self, path: str, kind: str, opts: Options) -> Document:
        doc = Document(path=path, kind=kind, backend=self.name)
        if kind == "epub":
            try:
                for label, text in _epub_chapters(path):
                    doc.add_page(text, method="epub-xhtml", label=label)
                if doc.pages:
                    return doc
            except zipfile.BadZipFile:
                pass  # fall through to fitz
        fitz = _try_import("fitz")
        if fitz is None:
            return Document.failed(
                path, "no engine for this e-book (pip install PyMuPDF)", kind)
        try:
            book = fitz.open(path)
        except Exception as exc:
            return Document.failed(path, f"open failed: {exc}", kind)
        for i in range(book.page_count):
            doc.add_page(book.load_page(i).get_text("text"),
                         method="fitz", label=f"page {i + 1}")
        book.close()
        return doc
