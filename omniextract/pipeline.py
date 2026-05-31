"""Batch driver: walk inputs, extract in parallel, cache by content hash.

OCR is CPU-bound and each task shells out to its own Tesseract, so a
ProcessPoolExecutor scales nearly linearly across cores. Results for unchanged
files are served from a sha256-keyed cache so re-running a big folder is cheap.
"""

import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Callable, List, Optional

from .backends.base import Options
from .core import extract
from .document import Document, Page

_SCALAR = ("ocr_lang", "ocr_psm", "ocr_pdf", "timeout", "dehyphenate",
           "max_archive_files", "max_archive_bytes", "max_depth")


def _opts_to_dict(opts: Options) -> dict:
    return {k: getattr(opts, k) for k in _SCALAR}


def iter_files(paths, follow_symlinks: bool = False):
    seen = set()
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p, followlinks=follow_symlinks):
                for name in sorted(files):
                    fp = os.path.join(root, name)
                    rp = os.path.realpath(fp)
                    if rp in seen:
                        continue
                    seen.add(rp)
                    yield fp
        elif os.path.isfile(p):
            yield p


def _hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _doc_from_dict(d: dict) -> Document:
    pages = [Page(**p) for p in d.get("pages", [])]
    kids = [_doc_from_dict(c) for c in d.get("children", [])]
    scalar = {k: v for k, v in d.items() if k not in ("pages", "children")}
    doc = Document(**scalar)
    doc.pages = pages
    doc.children = kids
    return doc


def _process(args):
    path, opts_dict, cache_dir = args
    if cache_dir:
        try:
            cpath = os.path.join(cache_dir, _hash(path) + ".json")
            if os.path.exists(cpath):
                with open(cpath, encoding="utf-8") as f:
                    doc = _doc_from_dict(json.load(f))
                doc.meta["cached"] = True
                return doc
        except Exception:
            pass
    doc = extract(path, Options(**opts_dict))
    if cache_dir and doc.ok:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            with open(os.path.join(cache_dir, _hash(path) + ".json"), "w",
                      encoding="utf-8") as f:
                f.write(doc.to_json())
        except Exception:
            pass
    return doc


def _run_sequential(args, total, progress) -> List[Document]:
    results = []
    for i, a in enumerate(args, 1):
        doc = _process(a)
        results.append(doc)
        if progress:
            progress(i, total, doc)
    return results


def _run_parallel(args, total, workers, progress) -> List[Document]:
    results = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_process, a): a[0] for a in args}
        done = 0
        for fut in as_completed(futs):
            done += 1
            try:
                doc = fut.result()
            except Exception as exc:
                doc = Document.failed(futs[fut], f"worker crashed: {exc}")
            results.append(doc)
            if progress:
                progress(done, total, doc)
    return results


def run(paths, opts: Optional[Options] = None, workers: Optional[int] = None,
        cache_dir: Optional[str] = None,
        progress: Optional[Callable] = None) -> List[Document]:
    opts = opts or Options()
    files = list(iter_files(paths))
    od = _opts_to_dict(opts)
    args = [(f, od, cache_dir) for f in files]
    total = len(files)

    if workers is None:
        workers = min(os.cpu_count() or 2, 8)

    if workers <= 1 or total <= 1:
        return _run_sequential(args, total, progress)

    try:
        return _run_parallel(args, total, workers, progress)
    except (RuntimeError, OSError, ImportError):
        # Parallelism unavailable (e.g. used as a library on Windows without
        # an `if __name__ == '__main__'` guard, or a restricted sandbox).
        # Fall back to sequential rather than failing the whole run.
        return _run_sequential(args, total, progress)
