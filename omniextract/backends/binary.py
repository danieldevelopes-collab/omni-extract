"""Last-resort backend for anything we couldn't otherwise read: pull printable
strings out of the bytes (like the Unix `strings` tool), both ASCII and
UTF-16LE (common in Windows binaries/blobs). Always produces *something* and is
always honest that this is a fallback."""

import os
import re

from ..document import Document
from .base import Backend, Options

_ASCII_RUN = re.compile(rb"[\x20-\x7e]{4,}")
_UTF16_RUN = re.compile(rb"(?:[\x20-\x7e]\x00){4,}")
_CAP = 64 * 1024 * 1024   # don't slurp more than 64 MB for strings scanning


class BinaryBackend(Backend):
    name = "binary"
    kinds = ("binary",)

    def extract(self, path: str, kind: str, opts: Options) -> Document:
        doc = Document(path=path, kind=kind, backend=self.name)
        try:
            size = os.path.getsize(path)
            doc.bytes_in = size
        except OSError:
            size = 0
        with open(path, "rb") as fh:
            data = fh.read(_CAP)
        if size > _CAP:
            doc.warnings.append(f"scanned first {_CAP // (1024*1024)} MB only")

        runs = [m.group().decode("ascii", "replace") for m in _ASCII_RUN.finditer(data)]
        u16 = [m.group().decode("utf-16-le", "replace") for m in _UTF16_RUN.finditer(data)]
        runs.extend(u16)

        doc.text = "\n".join(runs)
        doc.add_page(doc.text, method="strings")
        doc.meta["strings_found"] = len(runs)
        doc.warnings.append("unknown/binary type — printable-strings fallback")
        return doc
