"""Command-line interface.

    omni-extract FILE...              text to stdout
    omni-extract -f csv ./folder/     one row per document (great for batches)
    omni-extract -f json FILE         structured output (txt|json|jsonl|csv|md)
    omni-extract --out DIR PATHS...   write one file per input in --format
    omni-extract --serve              launch the local web UI in your browser
    omni-extract --capabilities       what's installed + install hints
"""

import argparse
import os
import re
import sys

from . import core, export, pipeline
from .backends.base import Options

_C = sys.stderr.isatty()
GREEN, YELLOW, GREY, DIM, RST = (
    ("\033[32m", "\033[33m", "\033[90m", "\033[2m", "\033[0m") if _C
    else ("", "", "", "", ""))


def _capabilities() -> int:
    print("omni-extract backends (✓ = ready, ✗ = needs install):\n")
    for name, kinds, ok, hint in core.capabilities():
        mark = f"{GREEN}✓{RST}" if ok else f"{YELLOW}✗{RST}"
        kinds_s = ", ".join(kinds)[:46]
        line = f"  {mark} {name.ljust(12)} {DIM}{kinds_s}{RST}"
        if hint:
            line += f"\n      {GREY}{hint}{RST}"
        print(line)
    print(f"\n  tesseract languages available: "
          f"{len(__import__('omniextract.ocr', fromlist=['languages']).languages())}")
    return 0


def _safe_name(path: str, taken: set) -> str:
    base = re.sub(r"[^\w.\-]+", "_", os.path.basename(path)) or "file"
    name = base
    i = 1
    while name in taken:
        name = f"{base}.{i}"
        i += 1
    taken.add(name)
    return name


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="omni-extract",
        description="Offline universal text extraction — any file, all its text.")
    ap.add_argument("paths", nargs="*", help="files and/or directories")
    ap.add_argument("--json", action="store_true", help="alias for --format json")
    ap.add_argument("--format", "-f", choices=list(export.FORMATS), default=None,
                    help="output format: txt | json | jsonl | csv | md "
                         "(csv/jsonl = one row per document, ideal for batches)")
    ap.add_argument("--out", metavar="DIR",
                    help="write one file per input in the chosen --format")
    ap.add_argument("--serve", action="store_true",
                    help="launch the local web UI in your browser")
    ap.add_argument("--port", type=int, default=0, help="port for --serve (0 = auto)")
    ap.add_argument("--no-open", action="store_true",
                    help="with --serve, don't auto-open the browser")
    ap.add_argument("--ocr-lang", default="eng", help="tesseract language(s), e.g. eng+fra")
    ap.add_argument("--ocr-psm", type=int, default=3, help="tesseract page-seg mode")
    ap.add_argument("--no-ocr-pdf", action="store_true", help="don't OCR scanned PDF pages")
    ap.add_argument("--workers", type=int, default=None, help="parallel workers")
    ap.add_argument("--cache", metavar="DIR", help="content-hash result cache dir")
    ap.add_argument("--timeout", type=float, default=120.0, help="per-file timeout (s)")
    ap.add_argument("--max-depth", type=int, default=4, help="archive recursion depth")
    ap.add_argument("--capabilities", action="store_true", help="show backends + exit")
    ap.add_argument("--quiet", "-q", action="store_true", help="no progress on stderr")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    if args.serve:
        from . import webapp
        webapp.serve(port=args.port, open_browser=not args.no_open)
        return 0
    if args.capabilities:
        return _capabilities()
    if not args.paths:
        ap.error("no input files (use --serve for the UI, or --capabilities)")

    fmt = args.format or ("json" if args.json else "txt")

    opts = Options(ocr_lang=args.ocr_lang, ocr_psm=args.ocr_psm,
                   ocr_pdf=not args.no_ocr_pdf, timeout=args.timeout,
                   max_depth=args.max_depth)

    totals = {"ok": 0, "fail": 0, "chars": 0}

    def progress(done, total, doc):
        totals["chars"] += doc.chars
        if doc.ok:
            totals["ok"] += 1
        else:
            totals["fail"] += 1
        if args.quiet:
            return
        tag = f"{GREEN}ok {RST}" if doc.ok else f"{YELLOW}fail{RST}"
        cached = f"{GREY}(cached){RST}" if doc.meta.get("cached") else ""
        sys.stderr.write(
            f"  [{done}/{total}] {tag} {doc.kind.ljust(11)} "
            f"{doc.chars:>7} chars  {os.path.basename(doc.path)} {cached}\n")
        sys.stderr.flush()

    results = pipeline.run(args.paths, opts=opts, workers=args.workers,
                           cache_dir=args.cache, progress=progress)

    # ---- output (single source of truth: the export module) ----
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        taken = set()
        for doc in results:
            stem = _safe_name(doc.path, taken)
            body = export.export_documents([doc], fmt)
            with open(os.path.join(args.out, stem + export.file_extension(fmt)),
                      "w", encoding="utf-8") as f:
                f.write(body)
        if not args.quiet:
            sys.stderr.write(
                f"  wrote {len(results)} file(s) to {args.out}/ as {fmt}\n")
    else:
        body = export.export_documents(results, fmt)
        sys.stdout.write(body)
        if body and not body.endswith("\n"):
            sys.stdout.write("\n")

    if not args.quiet:
        sys.stderr.write(
            f"\n  {GREEN}{totals['ok']} ok{RST} · {YELLOW}{totals['fail']} failed{RST} · "
            f"{totals['chars']} chars total\n")

    return 0 if totals["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
