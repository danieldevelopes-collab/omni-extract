"""Post-extraction text cleanup, shared by every backend.

Kept deliberately conservative — it must never *invent* or drop real content,
only tidy what extraction produced (Unicode form, stray control chars,
trailing whitespace, optional de-hyphenation of words split across line ends).
"""

import re
import unicodedata

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TRAILING_WS = re.compile(r"[ \t]+(\n|$)")
_MANY_BLANKS = re.compile(r"\n{3,}")
# word-hyphen-newline-word  ->  word+word  (PDF/column reflow)
_DEHYPHEN = re.compile(r"(\w)-\n(\w)")


def clean(text: str, dehyphenate: bool = True) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CTRL.sub("", text)
    if dehyphenate:
        text = _DEHYPHEN.sub(r"\1\2", text)
    text = _TRAILING_WS.sub(r"\1", text)
    text = _MANY_BLANKS.sub("\n\n", text)
    return text.strip()


def looks_meaningful(text: str, min_chars: int = 8) -> bool:
    """Heuristic: is there enough real text to call extraction a success?
    Used to decide when to fall back (e.g. PDF text → OCR)."""
    if not text:
        return False
    letters = sum(c.isalnum() for c in text)
    return letters >= min_chars
