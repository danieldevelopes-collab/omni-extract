"""The ordered set of backends and the routing table.

Backends are instantiated once. `backends_for(kind)` returns the candidates
for a detected kind, in the order `core` should try them. The binary
strings-extractor is the universal last resort for genuinely unknown bytes.
"""

from typing import List

from .backends.archive import ArchiveBackend
from .backends.base import Backend
from .backends.binary import BinaryBackend
from .backends.ebook import EbookBackend
from .backends.email_box import EmailBackend
from .backends.image import ImageBackend
from .backends.markup import MarkupBackend
from .backends.office import OfficeBackend
from .backends.pdf import PdfBackend
from .backends.plaintext import PlainTextBackend
from .backends.rtf import RtfBackend

_BINARY = BinaryBackend()

_BACKENDS: List[Backend] = [
    PlainTextBackend(),
    MarkupBackend(),
    OfficeBackend(),
    PdfBackend(),
    ImageBackend(),
    RtfBackend(),
    EbookBackend(),
    EmailBackend(),
    ArchiveBackend(),
    _BINARY,
]


def all_backends() -> List[Backend]:
    return list(_BACKENDS)


def backends_for(kind: str) -> List[Backend]:
    matched = [b for b in _BACKENDS if b.handles(kind)]
    return matched


def fallback_backend() -> Backend:
    return _BINARY
