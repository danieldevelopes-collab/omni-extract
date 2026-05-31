"""omni-extract — offline universal text extraction.

    from omniextract import extract
    doc = extract("scan.pdf")
    print(doc.text)

`extract(path)` returns a Document for any single file; `run_batch(paths)`
processes files/folders in parallel. Nothing here touches the network.
"""

from .backends.base import Options
from .core import capabilities, extract
from .document import Document, Page
from .export import FORMATS, export_documents
from .pipeline import iter_files
from .pipeline import run as run_batch

# `serve` (the local web UI) is intentionally a lazy import — it is reached via
# `from omniextract.webapp import serve` or the `--serve` CLI flag — so that the
# core import stays light and free of any HTTP machinery.

__version__ = "0.1.0"
__all__ = [
    "extract", "run_batch", "capabilities", "iter_files",
    "export_documents", "FORMATS",
    "Options", "Document", "Page", "__version__",
]
