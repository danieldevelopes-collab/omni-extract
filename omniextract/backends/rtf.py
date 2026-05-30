"""RTF → text with a self-contained control-word stripper (no striprtf dep).

Implements the well-known RTF de-tokenising algorithm: track group nesting and
ignorable destinations (fonttbl, pict, …), expand \\uN unicode and \\'xx hex
escapes, and translate \\par/\\tab/\\line into real whitespace.
"""

import re

from ..document import Document
from .base import Backend, Options

_DESTINATIONS = {
    "fonttbl", "colortbl", "stylesheet", "info", "pict", "object", "themedata",
    "colorschememapping", "latentstyles", "datastore", "generator", "mmath",
    "header", "footer", "headerf", "footerf", "headerl", "footerl",
    "headerr", "footerr", "pntext", "pntxta", "pntxtb",
}
_SPECIAL = {
    "par": "\n", "sect": "\n\n", "page": "\n\n", "line": "\n", "tab": "\t",
    "emdash": "—", "endash": "–", "lquote": "‘",
    "rquote": "’", "ldblquote": "“", "rdblquote": "”",
    "bullet": "•", "nbsp": " ",
}
_TOKEN = re.compile(
    r"\\([a-z]{1,32})(-?\d{1,10})?[ ]?|\\'([0-9a-fA-F]{2})|\\([^a-z])|([{}])|[\r\n]+|(.)",
    re.I | re.S)


def rtf_to_text(rtf: str) -> str:
    out, stack = [], []
    ignorable = False
    ucskip = 1
    curskip = 0
    for m in _TOKEN.finditer(rtf):
        word, arg, hexc, char, brace, tchar = m.groups()
        if brace == "{":
            stack.append((ucskip, ignorable))
        elif brace == "}":
            if stack:
                ucskip, ignorable = stack.pop()
        elif char is not None:
            if char == "~":
                out.append(" ")
            elif char in "{}\\":
                out.append(char)
            elif char == "*":
                ignorable = True
        elif word is not None:
            if word in _DESTINATIONS:
                ignorable = True
            elif word in _SPECIAL:
                if not ignorable:
                    out.append(_SPECIAL[word])
            elif word == "uc":
                ucskip = int(arg) if arg else 1
            elif word == "u":
                code = int(arg) if arg else 0
                if code < 0:
                    code += 0x10000
                if not ignorable:
                    out.append(chr(code) if 0 <= code <= 0x10FFFF else "?")
                curskip = ucskip
        elif hexc is not None:
            if curskip > 0:
                curskip -= 1
            elif not ignorable:
                out.append(chr(int(hexc, 16)))
        elif tchar is not None:
            if curskip > 0:
                curskip -= 1
            elif not ignorable:
                out.append(tchar)
    return "".join(out)


class RtfBackend(Backend):
    name = "rtf"
    kinds = ("rtf",)

    def extract(self, path: str, kind: str, opts: Options) -> Document:
        doc = Document(path=path, kind=kind, backend=self.name)
        with open(path, "rb") as fh:
            raw = fh.read()
        doc.bytes_in = len(raw)
        doc.text = rtf_to_text(raw.decode("latin-1", "replace"))
        doc.add_page(doc.text, method="rtf-strip")
        return doc
