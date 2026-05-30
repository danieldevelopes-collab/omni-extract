"""Plain text, source code, CSV/TSV, JSON, YAML, logs — anything that is
already text. The only real work is decoding with the right charset."""

from ..document import Document
from .base import Backend, Options

_TEXT_KINDS = ("text", "markdown")


def _decode(data: bytes):
    """Return (text, encoding_used, warnings)."""
    # 1) explicit BOMs
    for bom, enc in ((b"\xef\xbb\xbf", "utf-8-sig"),
                     (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16")):
        if data.startswith(bom):
            return data.decode(enc, "replace"), enc, []
    # 2) charset-normalizer if installed (better than chardet, pure-python)
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(data).best()
        if best is not None:
            return str(best), best.encoding, []
    except Exception:
        pass
    # 3) stdlib ladder
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc), enc, ([] if enc == "utf-8"
                                           else [f"decoded as {enc}"])
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace"), "utf-8/replace", ["lossy decode"]


class PlainTextBackend(Backend):
    name = "plaintext"
    kinds = _TEXT_KINDS

    def extract(self, path: str, kind: str, opts: Options) -> Document:
        doc = Document(path=path, kind=kind, backend=self.name)
        with open(path, "rb") as fh:
            data = fh.read()
        doc.bytes_in = len(data)
        text, enc, warns = _decode(data)
        doc.text = text
        doc.meta["encoding"] = enc
        doc.warnings += warns
        doc.add_page(text, method="decode", label=enc)
        return doc
