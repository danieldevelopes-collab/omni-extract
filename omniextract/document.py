"""The result types every backend returns.

A `Document` is the single, uniform output of the pipeline regardless of what
went in — a 500-page scanned PDF, a one-line .txt, or a .zip of mixed files.
It records not just the text but *how* the text was obtained, so nothing is
ever silently faked.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import json


@dataclass
class Page:
    """One logical unit of a document (a PDF page, a spreadsheet sheet, a
    slide, an image, or a single embedded file inside an archive)."""
    index: int
    text: str = ""
    method: str = ""                       # e.g. "pdf-text", "ocr", "docx-xml"
    confidence: Optional[float] = None      # 0..100 where a backend can report it
    label: str = ""                        # human label, e.g. "sheet: Budget"
    warnings: List[str] = field(default_factory=list)


@dataclass
class Document:
    """The uniform extraction result for one input file."""
    path: str
    kind: str = ""                         # detected kind, e.g. "pdf", "image/png"
    backend: str = ""                      # backend that produced this
    text: str = ""                         # full concatenated text
    pages: List[Page] = field(default_factory=list)
    chars: int = 0
    words: int = 0
    duration_ms: int = 0
    bytes_in: int = 0
    ok: bool = True                        # did we extract *something* meaningful
    error: str = ""                        # populated when ok is False
    warnings: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
    children: List["Document"] = field(default_factory=list)  # archive members

    def add_page(self, text: str, method: str, **kw) -> Page:
        p = Page(index=len(self.pages), text=text or "", method=method, **kw)
        self.pages.append(p)
        return p

    def finalize(self) -> "Document":
        """Assemble `text` from pages if needed and recompute counters."""
        if self.pages and not self.text:
            self.text = "\n\n".join(p.text for p in self.pages if p.text).strip()
        self.chars = len(self.text)
        self.words = len(self.text.split())
        # A document is "ok" if it has text, or honestly explains why not.
        if not self.text and not self.error and not self.children:
            self.ok = False
            if not self.warnings:
                self.warnings.append("no text found")
        return self

    def to_dict(self, include_text: bool = True) -> Dict[str, Any]:
        d = asdict(self)
        if not include_text:
            d.pop("text", None)
            for p in d.get("pages", []):
                p.pop("text", None)
        return d

    def to_json(self, indent: int = 2, include_text: bool = True) -> str:
        return json.dumps(self.to_dict(include_text), ensure_ascii=False,
                          indent=indent)

    @staticmethod
    def failed(path: str, error: str, kind: str = "") -> "Document":
        return Document(path=path, kind=kind, ok=False, error=error)
