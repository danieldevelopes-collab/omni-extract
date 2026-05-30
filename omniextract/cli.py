"""Command-line interface.

    omni-extract FILE...              text to stdout
    omni-extract --json FILE          structured JSON
    omni-extract --out DIR PATHS...   mirror .txt (+ .json) per input
    omni-extract --capabilities       what's installed + install hints
"""

import argparse
import json
import os
import re
import sys

from . import core, pipeline
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
    ap.add_argument("--json", action="store_true", help="emit structured JSON")
    ap.add_argument("--out", metavar="DIR", help="write <name>.txt (+ .json) per input")
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

    if args.capabilities:
        return _capabilities()
    if not args.paths:
        ap.error("no input files (or use --capabilities)")

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

    # ---- output ----
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        taken = set()
        for doc in results:
            stem = _safe_name(doc.path, taken)
            with open(os.path.join(args.out, stem + ".txt"), "w",
                      encoding="utf-8") as f:
                f.write(doc.text)
            with open(os.path.join(args.out, stem + ".json"), "w",
                      encoding="utf-8") as f:
                f.write(doc.to_json(include_text=False))
        if not args.quiet:
            sys.stderr.write(f"  wrote {len(results)} file(s) to {args.out}/\n")
    elif args.json:
        payload = [d.to_dict() for d in results]
        out = payload[0] if len(payload) == 1 else payload
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for i, doc in enumerate(results):
            if len(results) > 1:
                print(f"\n===== {doc.path} =====")
            sys.stdout.write(doc.text)
            if doc.text and not doc.text.endswith("\n"):
                sys.stdout.write("\n")

    if not args.quiet:
        sys.stderr.write(
            f"\n  {GREEN}{totals['ok']} ok{RST} · {YELLOW}{totals['fail']} failed{RST} · "
            f"{totals['chars']} chars total\n")

    return 0 if totals["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
