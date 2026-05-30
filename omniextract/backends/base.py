"""Backend contract + shared options.

A backend declares which `kinds` it handles, whether it's `available()` right
now (and a one-line install hint if not), and how to `extract()` a Document.
Backends are tried in registry order; `core` falls through to the next when one
yields too little text.
"""

from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from ..document import Document


@dataclass
class Options:
    ocr_lang: str = "eng"
    ocr_psm: int = 3
    ocr_pdf: bool = True              # OCR PDF pages that carry no embedded text
    timeout: float = 120.0           # per-file / per-engine wall-clock
    dehyphenate: bool = True
    # archive safety
    max_archive_files: int = 2000
    max_archive_bytes: int = 2_000_000_000
    max_depth: int = 4
    # internal: set by core so the archive backend can recurse
    extract_fn: Optional[Callable] = None
    _depth: int = 0


class Backend:
    name: str = "base"
    kinds: Tuple[str, ...] = ()

    def available(self) -> Tuple[bool, str]:
        """Return (ok, install_hint). Default: always available (stdlib)."""
        return True, ""

    def handles(self, kind: str) -> bool:
        return kind in self.kinds

    def extract(self, path: str, kind: str, opts: Options) -> Document:
        raise NotImplementedError


def _try_import(mod: str):
    try:
        return __import__(mod)
    except Exception:
        return None
