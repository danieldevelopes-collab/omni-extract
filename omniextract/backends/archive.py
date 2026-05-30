"""Archives — recurse into members and extract each, with bomb guards.

Handles zip and tar (incl. .tar.gz/.tar.bz2/.tar.xz), plus bare gzip/bzip2/xz
single-stream files. Each member is written to a temp file and run back through
the whole pipeline via `opts.extract_fn`, so an archive of mixed PDFs, images
and docs is fully mined. Limits cap member count, total bytes and depth.
"""

import bz2
import gzip
import lzma
import os
import tarfile
import tempfile
import zipfile

from ..document import Document
from .base import Backend, Options


def _zip_members(path, opts):
    with zipfile.ZipFile(path) as z:
        total = count = 0
        for info in z.infolist():
            if info.is_dir():
                continue
            count += 1
            total += info.file_size
            if count > opts.max_archive_files or total > opts.max_archive_bytes:
                break
            try:
                yield info.filename, z.read(info)
            except Exception:
                continue


def _tar_members(path, opts):
    with tarfile.open(path, "r:*") as t:
        total = count = 0
        for m in t:
            if not m.isfile():
                continue
            count += 1
            total += m.size
            if count > opts.max_archive_files or total > opts.max_archive_bytes:
                break
            f = t.extractfile(m)
            if f is None:
                continue
            try:
                yield m.name, f.read()
            except Exception:
                continue


def _single_stream(path, kind):
    opener = {"gzip": gzip.open, "bzip2": bz2.open, "xz": lzma.open}[kind]
    with opener(path, "rb") as f:
        data = f.read()
    name = os.path.basename(path)
    for ext in (".gz", ".bz2", ".xz", ".tgz"):
        if name.lower().endswith(ext):
            name = name[: -len(ext)]
            break
    return [(name, data)]


class ArchiveBackend(Backend):
    name = "archive"
    kinds = ("zip", "tar", "gzip", "bzip2", "xz")

    def extract(self, path: str, kind: str, opts: Options) -> Document:
        doc = Document(path=path, kind=kind, backend=self.name)
        if opts._depth >= opts.max_depth:
            doc.warnings.append(f"max depth {opts.max_depth} reached; not recursing")
            return doc
        if opts.extract_fn is None:
            doc.warnings.append("archive recursion not available in this context")
            return doc

        try:
            if kind == "zip":
                members = _zip_members(path, opts)
            elif kind == "tar":
                members = _tar_members(path, opts)
            else:
                # could be a compressed tar or a single compressed file
                try:
                    members = list(_tar_members(path, opts))
                except tarfile.ReadError:
                    members = _single_stream(path, kind)
        except Exception as exc:
            return Document.failed(path, f"archive open failed: {exc}", kind)

        child_opts = Options(**{**opts.__dict__})
        child_opts._depth = opts._depth + 1

        texts = []
        with tempfile.TemporaryDirectory(prefix="omni-arc-") as work:
            for i, (member_name, data) in enumerate(members):
                safe = f"m{i}_" + os.path.basename(member_name or f"member{i}")
                mpath = os.path.join(work, safe)
                try:
                    with open(mpath, "wb") as fh:
                        fh.write(data)
                    child = opts.extract_fn(mpath, child_opts)
                except Exception as exc:
                    child = Document.failed(member_name, str(exc))
                child.path = member_name        # show the in-archive name
                doc.children.append(child)
                if child.text:
                    texts.append(f"===== {member_name} =====\n{child.text}")

        doc.text = "\n\n".join(texts)
        doc.meta["members"] = len(doc.children)
        if not doc.children:
            doc.warnings.append("archive empty or all members unreadable")
        return doc
