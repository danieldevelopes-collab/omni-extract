"""The orchestration: detect → route → extract (with fallback) → normalize.

`extract(path)` is the one function the rest of the world calls. It never
raises on a bad file — it returns a Document whose `ok`/`error`/`warnings`
say exactly what happened.
"""

import time
from typing import Optional

from . import normalize, registry
from .backends.base import Options
from .detect import detect
from .document import Document


def _finish(doc: Document, opts: Options, start: float) -> Document:
    for p in doc.pages:
        p.text = normalize.clean(p.text, opts.dehyphenate)
    if doc.pages:
        doc.text = "\n\n".join(p.text for p in doc.pages if p.text).strip()
    elif doc.text:
        doc.text = normalize.clean(doc.text, opts.dehyphenate)
    doc.duration_ms = int((time.perf_counter() - start) * 1000)
    return doc.finalize()


def extract(path: str, opts: Optional[Options] = None) -> Document:
    """Extract all recoverable text from a single file."""
    opts = opts or Options()
    if opts.extract_fn is None:
        opts.extract_fn = extract            # wire archive recursion
    start = time.perf_counter()

    try:
        kind = detect(path)
    except Exception as exc:
        return Document.failed(path, f"detect failed: {exc}")

    candidates = registry.backends_for(kind) or [registry.fallback_backend()]

    best: Optional[Document] = None
    pending_hint = ""
    for backend in candidates:
        ok, hint = backend.available()
        if not ok:
            pending_hint = pending_hint or f"{backend.name}: {hint}"
            continue
        try:
            result = backend.extract(path, kind, opts)
        except Exception as exc:
            result = Document.failed(path, f"{backend.name} crashed: {exc}", kind)
        result.backend = result.backend or backend.name
        result.finalize()
        if result.ok and result.text.strip():
            return _finish(result, opts, start)
        if best is None or len(result.text) > len(best.text):
            best = result

    if best is None:                          # nothing was available to try
        doc = Document.failed(path, "no available backend", kind)
        if pending_hint:
            doc.warnings.append("hint: " + pending_hint)
        doc.duration_ms = int((time.perf_counter() - start) * 1000)
        return doc

    if pending_hint and not best.text.strip():
        best.warnings.append("hint: " + pending_hint)
    return _finish(best, opts, start)


def capabilities():
    """Return [(backend_name, kinds, available, hint), ...] for reporting."""
    rows = []
    for b in registry.all_backends():
        ok, hint = b.available()
        rows.append((b.name, b.kinds, ok, hint))
    return rows
