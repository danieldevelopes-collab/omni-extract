"""Turn extraction results into the shapes other tools actually consume.

The pipeline speaks `Document`; the outside world speaks files, pipes, and
HTTP bodies. This layer is the single, boring place that knows how each
serialization is spelled — so the CLI, a future web handler, and tests all
agree on exactly one definition of "the CSV" or "the JSONL". Standard library
only, because an offline tool should never need a wire format it can't emit on
a bare interpreter.
"""

import csv
import io
import json
from typing import List

from .document import Document

FORMATS = ("txt", "json", "jsonl", "csv", "md")

# How each format identifies itself over the wire and on disk. Keeping these
# beside the serializers means a new format is added in exactly one file.
_CONTENT_TYPES = {
    "txt": "text/plain; charset=utf-8",
    "json": "application/json; charset=utf-8",
    "jsonl": "application/x-ndjson; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
}

_EXTENSIONS = {
    "txt": ".txt",
    "json": ".json",
    "jsonl": ".jsonl",
    "csv": ".csv",
    "md": ".md",
}


def content_type(fmt: str) -> str:
    """MIME type (with charset) for a format, e.g. ``text/csv; charset=utf-8``."""
    try:
        return _CONTENT_TYPES[fmt]
    except KeyError:
        raise ValueError(f"unknown format: {fmt}")


def file_extension(fmt: str) -> str:
    """Filename suffix for a format, e.g. ``.csv`` (leading dot included)."""
    try:
        return _EXTENSIONS[fmt]
    except KeyError:
        raise ValueError(f"unknown format: {fmt}")


def export_documents(docs: List[Document], fmt: str,
                     include_text: bool = True) -> str:
    """Serialize a list of `Document` to one string in the requested format.

    `include_text` is threaded down to `Document.to_dict` and also drops the
    bulky text column/blocks from the human-facing formats, so the same call
    can produce a lightweight index or a full dump.
    """
    if fmt == "txt":
        return _to_txt(docs)
    if fmt == "json":
        return _to_json(docs, include_text)
    if fmt == "jsonl":
        return _to_jsonl(docs, include_text)
    if fmt == "csv":
        return _to_csv(docs, include_text)
    if fmt == "md":
        return _to_md(docs, include_text)
    raise ValueError(f"unknown format: {fmt}")


def _to_txt(docs: List[Document]) -> str:
    # A single document is just its text; only batches need separators so the
    # reader can tell where one file ends and the next begins.
    if len(docs) == 1:
        return docs[0].text or ""
    blocks = []
    for doc in docs:
        blocks.append(f"===== {doc.path} =====")
        blocks.append(doc.text or "")
    return "\n".join(blocks)


def _to_json(docs: List[Document], include_text: bool) -> str:
    return json.dumps([d.to_dict(include_text) for d in docs],
                      indent=2, ensure_ascii=False)


def _to_jsonl(docs: List[Document], include_text: bool) -> str:
    # One compact object per line: friendly to streaming and to batches of
    # near-identical "repeat documents" where pretty-printing only adds bulk.
    lines = [json.dumps(d.to_dict(include_text), ensure_ascii=False,
                        separators=(",", ":")) for d in docs]
    return "\n".join(lines)


def _to_csv(docs: List[Document], include_text: bool) -> str:
    header = ["path", "kind", "backend", "ok", "chars", "words",
              "duration_ms", "warnings"]
    if include_text:
        header.append("text")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for doc in docs:
        row = [
            doc.path or "",
            doc.kind or "",
            doc.backend or "",
            doc.ok,
            doc.chars or 0,
            doc.words or 0,
            doc.duration_ms or 0,
            "; ".join(doc.warnings or []),
        ]
        if include_text:
            row.append(doc.text or "")
        writer.writerow(row)
    return buf.getvalue()


def _to_md(docs: List[Document], include_text: bool) -> str:
    out = ["# Extraction report", ""]
    for doc in docs:
        out.append(f"## {doc.path}")
        out.append("")
        out.append(f"- kind: {doc.kind or ''}")
        out.append(f"- backend: {doc.backend or ''}")
        out.append(f"- chars: {doc.chars or 0}")
        out.append(f"- words: {doc.words or 0}")
        out.append(f"- duration_ms: {doc.duration_ms or 0}")
        out.append("")
        if include_text:
            out.append("```")
            out.append(doc.text or "")
            out.append("```")
            out.append("")
    return "\n".join(out)
