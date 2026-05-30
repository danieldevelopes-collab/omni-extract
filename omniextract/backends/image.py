"""Images → text via Tesseract OCR. The path that matters most for scanned
documents, screenshots, and photographed text."""

from .. import ocr
from ..document import Document
from .base import Backend, Options

_IMAGE_KINDS = ("image/png", "image/jpeg", "image/gif", "image/bmp",
                "image/tiff", "image/webp", "image/heic")


class ImageBackend(Backend):
    name = "image-ocr"
    kinds = _IMAGE_KINDS

    def available(self):
        if ocr.available():
            return True, ""
        return False, "install tesseract  (macOS: brew install tesseract  |  Linux: apt install tesseract-ocr)"

    def extract(self, path: str, kind: str, opts: Options) -> Document:
        doc = Document(path=path, kind=kind, backend=self.name)
        try:
            import os
            doc.bytes_in = os.path.getsize(path)
        except OSError:
            pass
        if not ocr.available():
            return Document.failed(path, "tesseract not installed", kind)

        text, conf, warns = ocr.image_to_text(
            path, lang=opts.ocr_lang, psm=opts.ocr_psm, timeout=opts.timeout)
        doc.warnings += warns
        doc.meta["ocr_lang"] = opts.ocr_lang
        doc.meta["ocr_psm"] = opts.ocr_psm
        if kind == "image/heic" and not text.strip():
            doc.warnings.append(
                "HEIC may need: pip install pillow pillow-heif")
        doc.add_page(text, method="ocr", confidence=conf)
        return doc
