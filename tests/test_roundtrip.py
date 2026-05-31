"""Round-trip proof: embed ONE canonical sentence into 10 genuinely different
file formats, extract each, and assert the text returns byte-for-byte
identical. PDF needs PyMuPDF; if it's absent that one case is skipped (the
other nine are pure standard library)."""

import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from omniextract import extract  # noqa: E402

CANON = "The quick brown fox jumps over the lazy dog and the sphinx of black quartz judges my vow."

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _write(path, data):
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(path, mode) as f:
        f.write(data)
    return path


def make_txt(p):  return _write(p, CANON)
def make_md(p):   return _write(p, CANON)
def make_html(p): return _write(p, f"<!doctype html><html><body><p>{CANON}</p></body></html>")
def make_xml(p):  return _write(p, f'<?xml version="1.0"?><doc><para>{CANON}</para></doc>')


def make_docx(p):
    body = f'<w:p><w:r><w:t>{CANON}</w:t></w:r></w:p>'
    doc = f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", doc)
    return p


def make_pptx(p):
    slide = (f'<?xml version="1.0"?><p:sld xmlns:p="{P}" xmlns:a="{A}">'
             f'<a:p><a:r><a:t>{CANON}</a:t></a:r></a:p></p:sld>')
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("ppt/presentation.xml", f'<p:presentation xmlns:p="{P}"/>')
        z.writestr("ppt/slides/slide1.xml", slide)
    return p


def make_xlsx(p):
    sheet = (f'<?xml version="1.0"?><worksheet xmlns="{S}"><sheetData>'
             f'<row r="1"><c r="A1" t="inlineStr"><is><t>{CANON}</t></is></c>'
             f'</row></sheetData></worksheet>')
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{S}"/>')
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return p


def make_rtf(p):
    return _write(p, "{\\rtf1\\ansi " + CANON + "}")


def make_epub(p):
    xhtml = ('<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
             f'<body><p>{CANON}</p></body></html>')
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", "<container/>")
        z.writestr("content.opf", "<package/>")
        z.writestr("chapter1.xhtml", xhtml)
    return p


def make_pdf(p):
    import fitz  # PyMuPDF
    doc = fitz.open()
    page = doc.new_page(width=1400, height=200)
    page.insert_text((36, 96), CANON, fontsize=16)
    doc.save(p)
    doc.close()
    return p


GENERATORS = [
    ("txt", ".txt", make_txt),
    ("markdown", ".md", make_md),
    ("html", ".html", make_html),
    ("xml", ".xml", make_xml),
    ("docx", ".docx", make_docx),
    ("pptx", ".pptx", make_pptx),
    ("xlsx", ".xlsx", make_xlsx),
    ("rtf", ".rtf", make_rtf),
    ("epub", ".epub", make_epub),
    ("pdf", ".pdf", make_pdf),
]


def run(verbose=True):
    results = []
    with tempfile.TemporaryDirectory(prefix="omni-rt-") as work:
        for label, ext, gen in GENERATORS:
            path = os.path.join(work, "case" + ext)
            try:
                gen(path)
            except ImportError:
                results.append((label, None, "SKIP (PyMuPDF not installed)"))
                continue
            doc = extract(path)
            exact = (doc.text == CANON)
            results.append((label, exact, doc.text))
    if verbose:
        print(f'  canonical: "{CANON}"\n')
        print(f"  {'format':10} {'backend kind':14} exact?  extracted")
        print("  " + "-" * 78)
        for label, exact, text in results:
            if exact is None:
                mark = "skip"
                shown = text
            else:
                mark = "MATCH" if exact else "DIFF "
                shown = (text or "")[:38] + ("…" if len(text or "") > 38 else "")
            print(f"  {label:10} {'':14} {mark:6}  {shown}")
        tested = [r for r in results if r[1] is not None]
        passed = sum(1 for r in tested if r[1])
        print("  " + "-" * 78)
        print(f"  {passed}/{len(tested)} formats round-tripped byte-for-byte "
              f"({len(results) - len(tested)} skipped)")
    return results


# pytest-style assertions (PDF skipped if PyMuPDF missing)
def test_roundtrip_all_formats():
    for label, exact, text in run(verbose=False):
        if exact is None:
            continue
        assert exact, f"{label} did not round-trip: got {text!r}"


if __name__ == "__main__":
    res = run(verbose=True)
    tested = [r for r in res if r[1] is not None]
    sys.exit(0 if all(r[1] for r in tested) else 1)
