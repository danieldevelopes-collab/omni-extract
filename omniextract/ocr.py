"""OCR via the Tesseract engine, called as a subprocess (no pytesseract dep).

Why subprocess rather than a binding: zero Python dependency, full control of
flags, and the engine is killed cleanly on timeout. Pillow is used *if present*
to preprocess the image (grayscale + autocontrast + sensible upscaling), which
makes Tesseract both faster and more accurate; without Pillow we hand the raw
file straight to the engine (Tesseract reads png/jpg/tiff/bmp/gif/webp itself).
"""

import os
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple

from .portable import kill_tree, popen_isolation_kwargs

# leptonica (bundled with tesseract) reads these directly:
_TESS_NATIVE = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif",
                ".webp", ".pnm", ".jp2"}


def tesseract_path() -> Optional[str]:
    return shutil.which("tesseract")


def available() -> bool:
    return tesseract_path() is not None


def languages() -> List[str]:
    exe = tesseract_path()
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "--list-langs"], capture_output=True,
                             text=True, timeout=10)
        return [l.strip() for l in out.stdout.splitlines()
                if l.strip() and " " not in l.strip()]
    except Exception:
        return []


def _pillow():
    try:
        from PIL import Image, ImageOps  # noqa
        return Image, ImageOps
    except Exception:
        return None, None


def _preprocess(src_path: str, work_dir: str) -> Tuple[str, List[str]]:
    """Return (path_to_feed_tesseract, warnings). Uses Pillow when available."""
    Image, ImageOps = _pillow()
    if Image is None:
        ext = os.path.splitext(src_path)[1].lower()
        if ext in _TESS_NATIVE:
            return src_path, []
        return src_path, ["Pillow not installed: feeding raw file to tesseract"]
    try:
        im = Image.open(src_path)
        # HEIC and friends need pillow-heif registered; if that failed, Image
        # .open raises and we fall through to the raw path below.
        im = ImageOps.exif_transpose(im)        # honor camera rotation
        im = im.convert("L")                    # grayscale
        im = ImageOps.autocontrast(im)
        # upscale small images — OCR likes ~300 DPI-ish glyph sizes
        w, h = im.size
        longest = max(w, h)
        if longest < 1800:
            scale = min(3.0, 1800 / max(longest, 1))
            im = im.resize((int(w * scale), int(h * scale)))
        out = os.path.join(work_dir, "pre.png")
        im.save(out)
        return out, []
    except Exception as exc:
        return src_path, [f"preprocess skipped: {exc}"]


def image_to_text(path: str, lang: str = "eng", psm: int = 3,
                  timeout: float = 120.0):
    """OCR an image file. Returns (text, confidence_or_None, warnings)."""
    exe = tesseract_path()
    if not exe:
        return "", None, ["tesseract not installed"]

    with tempfile.TemporaryDirectory(prefix="omni-ocr-") as work:
        feed, warns = _preprocess(path, work)
        cmd = [exe, feed, "stdout", "-l", lang, "--psm", str(psm)]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                **popen_isolation_kwargs())
        except OSError as exc:
            return "", None, warns + [f"tesseract launch failed: {exc}"]
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            try:
                proc.communicate(timeout=5)
            except Exception:
                pass
            return "", None, warns + [f"OCR timed out after {timeout:g}s"]

        text = out.decode("utf-8", "replace")
        if proc.returncode != 0 and not text.strip():
            msg = err.decode("utf-8", "replace").strip().splitlines()
            warns.append("tesseract error: " + (msg[-1] if msg else "unknown"))
        return text, None, warns


def image_bytes_to_text(data: bytes, suffix: str = ".png", **kw):
    """OCR raw image bytes (used for PDF page rasters)."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
        tf.write(data)
        tmp = tf.name
    try:
        return image_to_text(tmp, **kw)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
