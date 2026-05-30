"""Decide what a file *is* — robustly, and without trusting the extension.

Strategy (cheap → precise):
  1. magic-byte signatures on the first chunk (authoritative when they match),
  2. container sniffing for the ambiguous ones (a `PK\\x03\\x04` file might be a
     .docx, .xlsx, .pptx, .epub, or a plain .zip; a `RIFF` file might be .webp,
     .wav or .avi),
  3. extension as a hint,
  4. a UTF-8/text heuristic,
  5. otherwise: "binary".

Only the first few KB are read, so detection stays O(1) on huge files.
"""

import os
import zipfile

_READ = 65536  # bytes sniffed from the head

# (offset, signature, kind)
_MAGIC = [
    (0, b"%PDF-", "pdf"),
    (0, b"\x89PNG\r\n\x1a\n", "image/png"),
    (0, b"\xff\xd8\xff", "image/jpeg"),
    (0, b"GIF87a", "image/gif"),
    (0, b"GIF89a", "image/gif"),
    (0, b"BM", "image/bmp"),
    (0, b"II*\x00", "image/tiff"),
    (0, b"MM\x00*", "image/tiff"),
    (4, b"ftypheic", "image/heic"),
    (4, b"ftypheix", "image/heic"),
    (4, b"ftypmif1", "image/heic"),
    (0, b"\x1f\x8b", "gzip"),
    (0, b"BZh", "bzip2"),
    (0, b"\xfd7zXZ\x00", "xz"),
    (0, b"7z\xbc\xaf\x27\x1c", "7z"),
    (0, b"Rar!\x1a\x07", "rar"),
    (0, b"{\\rtf", "rtf"),
    (0, b"SQLite format 3\x00", "sqlite"),
    (257, b"ustar", "tar"),
]

_EXT = {
    ".txt": "text", ".text": "text", ".log": "text", ".csv": "text",
    ".tsv": "text", ".json": "text", ".yaml": "text", ".yml": "text",
    ".ini": "text", ".toml": "text", ".srt": "text", ".vtt": "text",
    ".py": "text", ".js": "text", ".ts": "text", ".c": "text", ".h": "text",
    ".cpp": "text", ".java": "text", ".rb": "text", ".go": "text",
    ".rs": "text", ".sh": "text", ".sql": "text", ".tex": "text",
    ".md": "markdown", ".markdown": "markdown", ".rst": "text",
    ".html": "html", ".htm": "html", ".xhtml": "html", ".xml": "xml",
    ".pdf": "pdf", ".rtf": "rtf",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".bmp": "image/bmp", ".tif": "image/tiff",
    ".tiff": "image/tiff", ".webp": "image/webp", ".heic": "image/heic",
    ".heif": "image/heic",
    ".docx": "docx", ".xlsx": "xlsx", ".pptx": "pptx",
    ".doc": "doc", ".xls": "xls", ".ppt": "ppt",
    ".odt": "odf", ".ods": "odf", ".odp": "odf",
    ".epub": "epub", ".mobi": "ebook", ".fb2": "ebook", ".cbz": "ebook",
    ".xps": "ebook",
    ".eml": "email", ".mbox": "mbox", ".msg": "outlook",
    ".zip": "zip", ".tar": "tar", ".gz": "gzip", ".tgz": "gzip",
    ".bz2": "bzip2", ".xz": "xz", ".7z": "7z", ".rar": "rar",
    ".sqlite": "sqlite", ".db": "sqlite",
    ".mp3": "audio", ".wav": "audio", ".m4a": "audio", ".flac": "audio",
    ".mp4": "video", ".mov": "video", ".mkv": "video", ".avi": "video",
}

# kinds that are zip containers needing a closer look
_ZIP_CONTAINERS = {
    "word/document.xml": "docx",
    "xl/workbook.xml": "xlsx",
    "ppt/presentation.xml": "pptx",
    "mimetype": "epub",          # epub stores its mimetype as the first entry
    "content.opf": "epub",
}


def _match_magic(head: bytes):
    for off, sig, kind in _MAGIC:
        if head[off:off + len(sig)] == sig:
            return kind
    return None


def _sniff_zip(path: str):
    """A PK-zip could be docx/xlsx/pptx/epub/odf or a plain archive."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            if "word/document.xml" in names:
                return "docx"
            if "xl/workbook.xml" in names:
                return "xlsx"
            if "ppt/presentation.xml" in names:
                return "pptx"
            if any(n.endswith(".opf") for n in names) or "mimetype" in names:
                try:
                    mt = zf.read("mimetype").strip()
                    if mt == b"application/epub+zip":
                        return "epub"
                except KeyError:
                    pass
                if any(n.endswith(".opf") for n in names):
                    return "epub"
            if "content.xml" in names:      # OpenDocument
                return "odf"
    except (zipfile.BadZipFile, OSError):
        return "zip"
    return "zip"


def _sniff_riff(head: bytes):
    tag = head[8:12]
    if tag == b"WEBP":
        return "image/webp"
    if tag == b"WAVE":
        return "audio"
    if tag == b"AVI ":
        return "video"
    return "binary"


def _looks_text(head: bytes) -> bool:
    if not head:
        return True
    if b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
        return True
    except UnicodeDecodeError:
        # allow a small tail of a multibyte char split at the boundary
        try:
            head[:-3].decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False


def detect(path: str) -> str:
    """Return a normalized kind string for `path`."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(_READ)
    except OSError:
        return "binary"

    kind = _match_magic(head)

    if head[:4] == b"RIFF":
        return _sniff_riff(head)

    if kind == "pdf":
        return "pdf"
    if kind and kind.startswith("image/"):
        return kind
    if kind in ("rtf", "sqlite", "gzip", "bzip2", "xz", "7z", "rar", "tar"):
        return kind

    if head[:4] == b"PK\x03\x04":
        return _sniff_zip(path)

    # extension hint (helps text-family + things magic can't tell apart)
    ext = os.path.splitext(path)[1].lower()
    if ext in _EXT:
        guess = _EXT[ext]
        # don't let a wrong extension override a strong text/binary signal
        if guess == "text" and not _looks_text(head):
            return "binary"
        return guess

    if _looks_text(head):
        # try to refine common structured text by content
        stripped = head.lstrip()[:1]
        if stripped in (b"<",):
            return "xml"
        return "text"

    return "binary"
