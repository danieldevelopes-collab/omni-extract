# omni-extract

> Feed it **any file** — a scanned PDF, a screenshot, a Word doc, an email, a
> zip full of mixed junk — and get back **all the text it can possibly
> recover**. Fully **offline**. Fast. Never crashes, never fabricates.

**By Daniel Bratcher · [@danieldevelopes-collab](https://github.com/danieldevelopes-collab)**
· MIT licensed · Python 3 · **core has zero third-party dependencies**

```bash
omni-extract scan.pdf                 # → text on stdout
omni-extract --json invoice.png       # → structured JSON
omni-extract --out text/ ./inbox/     # → mirror a folder to .txt files
omni-extract --capabilities           # → what's installed + how to get the rest
```

---

## Why it's different

Most "extract text" tools are a thin wrapper around one library and fall over
the moment you hand them a file type they didn't expect. omni-extract is built
the other way round:

- **Any file resolves to *something*.** Known types get a real backend; truly
  unknown bytes fall back to printable-strings extraction. It never throws on a
  bad file — it returns a result that says exactly what happened.
- **It doesn't trust the extension.** Detection is by magic bytes + container
  sniffing first (a `.txt` that is really a PDF is handled as a PDF; a `.docx`
  that is really a plain zip is handled as a zip).
- **Scanned vs. digital is automatic.** A born-digital PDF uses its embedded
  text instantly; only the pages that come back empty (i.e. scans) get
  rasterised and sent to OCR. A 500-page text PDF never wakes the OCR engine.
- **Offline, always.** No cloud OCR, no telemetry, no network. Local engines
  only.

---

## How it works

```
file → DETECT → ROUTE → EXTRACT (with fallback chain) → NORMALIZE → Document(text + metadata)
```

1. **Detect** — magic-byte signatures, then container sniffing for the
   ambiguous ones (a `PK\x03\x04` is a .docx / .xlsx / .pptx / .epub / plain
   zip; a `RIFF` is .webp / .wav / .avi), then extension, then a UTF-8 text
   heuristic. Reads only the first 64 KB, so detection is O(1) on huge files.
2. **Route** — a registry maps the detected kind to an ordered list of
   backends, each declaring whether it's available right now.
3. **Extract with fallback** — try the best backend; if it yields too little
   text, fall through. The key hybrid lives in the PDF backend: embedded text
   first, OCR only the empty pages.
4. **Normalize** — Unicode NFC, control-char strip, de-hyphenation of words
   split across line ends, whitespace tidy → a uniform `Document`.

Every result records **which backend ran, the method per page, and any
warnings** — so nothing is ever silently faked.

---

## Coverage

| Family | Types | Engine | Needs |
|---|---|---|---|
| Plain text | txt, log, csv, tsv, json, yaml, ini, source code | stdlib + charset detect | — |
| Markup | html, xml, xhtml | stdlib `html.parser` | — |
| **Office** | **docx, xlsx, pptx** | **stdlib** (OOXML = zip+XML) | — |
| **PDF** | pdf (digital **and** scanned) | PyMuPDF + OCR fallback | `PyMuPDF`, tesseract |
| **Images** | png, jpg, tiff, bmp, gif, webp, heic | Tesseract OCR | tesseract, `Pillow` |
| RTF | rtf | stdlib (self-contained stripper) | — |
| E-book | epub (stdlib), mobi/fb2/cbz/xps | stdlib / PyMuPDF | — / `PyMuPDF` |
| Email | eml, mbox | stdlib `email` | — |
| Archives | zip, tar, gz, bz2, xz | recurse into every member | stdlib |
| Unknown/binary | *anything else* | printable-strings (ASCII + UTF-16) | — |

The headline: **everything except PDFs and image-OCR runs on the standard
library alone.** The only external pieces are **tesseract** (for pixels) and
**PyMuPDF** (for PDFs).

---

## Efficiency

- **Lazy imports** — heavy libs load only when a matching file actually appears.
- **Hybrid PDF** — embedded text first; OCR (and rasterisation) only for the
  pages that need it.
- **Parallel batch** — `ProcessPoolExecutor` across files; OCR is CPU-bound and
  each task shells out to its own Tesseract, so it scales across cores.
- **OCR preprocessing** — grayscale → autocontrast → upscale small images:
  faster *and* more accurate.
- **Content-hash cache** — `--cache DIR` keys results by sha256, so re-running a
  big folder skips unchanged files.
- **Guards** — per-file timeout (OCR can hang), archive-bomb limits
  (files / bytes / depth), symlink-loop guard on directory walks.

---

## Install

**Core (zero dependencies)** — already handles text, html/xml, docx/xlsx/pptx,
rtf, epub, email, archives, and the strings fallback:

```bash
git clone https://github.com/danieldevelopes-collab/omni-extract.git
cd omni-extract
python3 -m omniextract --capabilities      # see what you've already got
```

**Full (PDF + image OCR):**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt            # PyMuPDF, Pillow, charset-normalizer
# system OCR engine:
brew install tesseract tesseract-lang      # macOS
# sudo apt install tesseract-ocr           # Debian/Ubuntu
```

`omni-extract --capabilities` always tells you what's live and the one-line
install hint for anything that isn't.

---

## Usage

### CLI
```bash
omni-extract FILE...                  # text to stdout (headers when multiple)
omni-extract --json FILE              # structured Document as JSON
omni-extract --out DIR PATHS...       # write <name>.txt (+ .json) per input
omni-extract --ocr-lang eng+fra IMG   # OCR languages (163 available)
omni-extract --workers 8 ./folder/    # parallelism
omni-extract --cache .cache ./folder/ # skip unchanged files on re-run
omni-extract --no-ocr-pdf scan.pdf    # disable the OCR fallback
omni-extract --capabilities           # backends + install hints
```

### Library
```python
from omniextract import extract, run_batch, Options

doc = extract("invoice.png")
print(doc.text)
print(doc.kind, doc.backend, doc.words, "words", doc.duration_ms, "ms")
for page in doc.pages:
    print(page.label, page.method, page.confidence)

# batch a folder in parallel
docs = run_batch(["./inbox"], opts=Options(ocr_lang="eng"), workers=8)
```

A `Document` is the uniform result for every input: `.text`, `.pages[]`,
`.kind`, `.backend`, `.chars`, `.words`, `.duration_ms`, `.ok`, `.error`,
`.warnings`, `.meta`, and `.children[]` (for archive members).

---

## Honesty

- **100% offline.** No network calls anywhere. No telemetry. OCR is local
  (Tesseract); PDFs are local (PyMuPDF).
- **No fabricated text.** If a backend can't read a file, the result says so —
  with the reason and the install hint — instead of inventing content.
- **Confidence and method are recorded per page**, so you always know whether a
  given line came from embedded text, OCR, or a strings fallback.
- **Coverage is honest about its limits.** Legacy binary Office (.doc/.xls/.ppt)
  needs LibreOffice; iPhone .heic needs `pillow-heif`; .7z needs `py7zr`;
  Outlook .msg needs `extract-msg`. Each is detected and reported rather than
  silently mangled.

---

## License

[MIT](LICENSE) © 2026 Daniel Bratcher (danieldevelopes-collab).
