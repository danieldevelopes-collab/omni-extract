"""Format guarantees for the export layer, stdlib only so they run anywhere.

These don't extract anything real — they hand-build `Document` objects and pin
down the invariants other programs rely on: the CSV header is exactly this, a
JSONL line is parseable JSON, every document's text survives the txt dump.
Runs both under pytest and as a plain script that prints `all passed`.
"""

import csv
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from omniextract.document import Document, Page  # noqa: E402
from omniextract import export  # noqa: E402


def _docs():
    """Three deliberately varied documents: clean text, a doc with warnings
    plus a field that needs CSV quoting, and a failed/empty extraction."""
    a = Document(
        path="/tmp/a.txt", kind="txt", backend="text",
        text="hello world", chars=11, words=2, duration_ms=3, ok=True,
        pages=[Page(index=0, text="hello world", method="text")],
    )
    # Text here deliberately holds a comma and quotes (which the csv module
    # must escape) but no newline, so "one physical line per row" still holds.
    b = Document(
        path="/tmp/b.csv", kind="csv", backend="text",
        text='line one, with comma and "quotes" inside', chars=40, words=7,
        duration_ms=9, ok=True, warnings=["partial", "guessed encoding"],
    )
    c = Document.failed("/tmp/c.bin", "no text found", kind="binary")
    return [a, b, c]


def test_formats_constant():
    assert export.FORMATS == ("txt", "json", "jsonl", "csv", "md")


def test_csv_header_and_rows():
    docs = _docs()
    out = export.export_documents(docs, "csv")
    rows = list(csv.reader(io.StringIO(out)))
    assert rows[0] == ["path", "kind", "backend", "ok", "chars", "words",
                       "duration_ms", "warnings", "text"]
    # N+1 non-empty lines: one header plus one row per document.
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == len(docs) + 1
    # Warnings joined by "; " and embedded commas/quotes survived the trip.
    assert rows[2][7] == "partial; guessed encoding"
    assert "line one, with comma" in rows[2][8]


def test_csv_without_text_drops_column():
    out = export.export_documents(_docs(), "csv", include_text=False)
    header = next(csv.reader(io.StringIO(out)))
    assert header == ["path", "kind", "backend", "ok", "chars", "words",
                      "duration_ms", "warnings"]
    assert "text" not in header


def test_jsonl_lines_parse():
    docs = _docs()
    out = export.export_documents(docs, "jsonl")
    lines = out.splitlines()
    assert len(lines) == len(docs)
    for ln in lines:
        obj = json.loads(ln)  # each line is independently valid JSON
        assert "path" in obj
    # Compact: a single line carries no indentation padding.
    assert "\n  " not in lines[0]


def test_json_is_list_of_n():
    docs = _docs()
    parsed = json.loads(export.export_documents(docs, "json"))
    assert isinstance(parsed, list) and len(parsed) == len(docs)
    parsed_no_text = json.loads(
        export.export_documents(docs, "json", include_text=False))
    assert "text" not in parsed_no_text[0]


def test_txt_contains_every_text_and_headers():
    docs = _docs()
    out = export.export_documents(docs, "txt")
    for doc in docs:
        if doc.text:
            assert doc.text in out
        assert f"===== {doc.path} =====" in out


def test_txt_single_doc_has_no_header():
    one = _docs()[:1]
    out = export.export_documents(one, "txt")
    assert out == "hello world"
    assert "=====" not in out


def test_md_has_heading_per_doc():
    docs = _docs()
    out = export.export_documents(docs, "md")
    assert out.startswith("# Extraction report")
    assert out.count("## ") == len(docs)
    for doc in docs:
        assert f"## {doc.path}" in out


def test_unknown_format_raises():
    for fn in (lambda: export.export_documents(_docs(), "xml"),
               lambda: export.content_type("xml"),
               lambda: export.file_extension("xml")):
        try:
            fn()
        except ValueError as exc:
            assert "unknown format" in str(exc)
        else:
            raise AssertionError("expected ValueError for unknown format")


def test_content_type_and_extension():
    assert export.content_type("csv") == "text/csv; charset=utf-8"
    assert export.file_extension("csv") == ".csv"
    for fmt in export.FORMATS:
        assert export.content_type(fmt)
        assert export.file_extension(fmt).startswith(".")


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL  {name}: {exc}")
            except Exception as exc:
                failures += 1
                print(f"  ERROR {name}: {exc!r}")
    print(f"\n{'all passed' if not failures else str(failures) + ' failed'}")
    sys.exit(1 if failures else 0)
