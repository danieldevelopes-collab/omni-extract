"""Smoke tests that run with zero third-party deps (stdlib backends only),
so they pass in any CI without PyMuPDF/Pillow/tesseract installed."""

import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from omniextract import extract  # noqa: E402
from omniextract.detect import detect  # noqa: E402


def _tmp(content, suffix):
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(content if isinstance(content, bytes) else content.encode())
    return path


def test_plaintext():
    doc = extract(_tmp("hello world 123", ".txt"))
    assert doc.ok and "hello world 123" in doc.text


def test_json_is_text():
    doc = extract(_tmp('{"a": 1, "b": "x"}', ".json"))
    assert doc.ok and '"b": "x"' in doc.text


def test_html_drops_script_and_style():
    doc = extract(_tmp(
        "<style>p{}</style><p>keep me</p><script>drop_me()</script>", ".html"))
    assert "keep me" in doc.text
    assert "drop_me" not in doc.text


def test_docx_ooxml():
    path = _tmp(b"", ".docx")
    body = "<w:p><w:r><w:t>Hello DOCX world</w:t></w:r></w:p>"
    document = ('<?xml version="1.0"?><w:document '
                'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:body>' + body + '</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", document)
    doc = extract(path)
    assert doc.ok and "Hello DOCX world" in doc.text
    assert doc.backend == "office"


def test_zip_recursion():
    path = _tmp(b"", ".zip")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("inner/note.txt", "secret inside archive")
    doc = extract(path)
    assert "secret inside archive" in doc.text
    assert doc.children and doc.children[0].ok


def test_unknown_falls_back_to_strings():
    doc = extract(_tmp(b"\x00\x01\x02FINDME_MARKER\x7f\xfe", ".bin"))
    assert "FINDME_MARKER" in doc.text
    assert doc.backend == "binary"


def test_detection_trusts_content_over_extension():
    # PDF bytes with a .txt extension must be detected as pdf, not text.
    assert detect(_tmp(b"%PDF-1.7\n...", ".txt")) == "pdf"
    # zip magic with a .docx extension but no word/ part -> plain zip
    p = _tmp(b"", ".docx")
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("hello.txt", "x")
    assert detect(p) == "zip"


def test_never_raises_on_empty_file():
    doc = extract(_tmp(b"", ".dat"))
    assert doc is not None  # returns a Document, does not throw


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
