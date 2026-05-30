"""PDF → text with the key hybrid strategy:

  * read each page's *embedded* text first (instant, exact);
  * only pages that come back essentially empty (i.e. scanned images) get
    rasterised and sent to OCR;

so a 500-page born-digital PDF never touches Tesseract, while a scanned one is
fully recovered. Engine: PyMuPDF (fitz) when available; otherwise poppler's
`pdftotext` for text-only extraction.
"""

import shutil
import subprocess

from .. import normalize, ocr
from ..document import Document
from .base import Backend, Options, _try_import


class PdfBackend(Backend):
    name = "pdf"
    kinds = ("pdf",)

    def available(self):
        if _try_import("fitz") is not None:
            return True, ""
        if shutil.which("pdftotext"):
            return True, "(text-only; pip install PyMuPDF to OCR scanned PDFs)"
        return False, "pip install PyMuPDF   (or install poppler for pdftotext)"

    def extract(self, path: str, kind: str, opts: Options) -> Document:
        doc = Document(path=path, kind=kind, backend=self.name)
        try:
            import os
            doc.bytes_in = os.path.getsize(path)
        except OSError:
            pass

        fitz = _try_import("fitz")
        if fitz is not None:
            return self._with_fitz(fitz, path, opts, doc)
        if shutil.which("pdftotext"):
            return self._with_pdftotext(path, opts, doc)
        return Document.failed(path, "no PDF engine (pip install PyMuPDF)", kind)

    def _with_fitz(self, fitz, path, opts, doc):
        try:
            pdf = fitz.open(path)
        except Exception as exc:
            return Document.failed(path, f"open failed: {exc}", "pdf")

        ocr_ready = opts.ocr_pdf and ocr.available()
        ocr_pages = 0
        for i in range(pdf.page_count):
            page = pdf.load_page(i)
            text = page.get_text("text")
            if normalize.looks_meaningful(text):
                doc.add_page(text, method="pdf-text", label=f"page {i + 1}")
                continue
            if ocr_ready:
                try:
                    pix = page.get_pixmap(dpi=200)
                    png = pix.tobytes("png")
                    otext, conf, warns = ocr.image_bytes_to_text(
                        png, lang=opts.ocr_lang, psm=opts.ocr_psm,
                        timeout=opts.timeout)
                    p = doc.add_page(otext, method="ocr", confidence=conf,
                                     label=f"page {i + 1}")
                    p.warnings += warns
                    ocr_pages += 1
                except Exception as exc:
                    doc.add_page(text, method="pdf-text", label=f"page {i + 1}",
                                 warnings=[f"OCR failed: {exc}"])
            else:
                p = doc.add_page(text, method="pdf-text", label=f"page {i + 1}")
                if not text.strip():
                    p.warnings.append(
                        "empty page — looks scanned; OCR disabled/unavailable")
        doc.meta["pages"] = pdf.page_count
        doc.meta["ocr_pages"] = ocr_pages
        if ocr_pages and not ocr.available():
            doc.warnings.append("scanned pages present but tesseract missing")
        pdf.close()
        return doc

    def _with_pdftotext(self, path, opts, doc):
        try:
            out = subprocess.run(["pdftotext", "-layout", path, "-"],
                                 capture_output=True, timeout=opts.timeout)
            text = out.stdout.decode("utf-8", "replace")
        except Exception as exc:
            return Document.failed(path, f"pdftotext failed: {exc}", "pdf")
        doc.add_page(text, method="pdftotext")
        doc.meta["engine"] = "pdftotext"
        if not normalize.looks_meaningful(text):
            doc.warnings.append(
                "little/no embedded text — scanned PDF needs PyMuPDF for OCR")
        return doc
