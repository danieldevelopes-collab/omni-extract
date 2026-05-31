"""A tiny, dependency-free local web UI for omni-extract.

Design: a single `ThreadingHTTPServer` (stdlib only) bound to loopback that
serves a one-page app from `omniextract/web/` and a small JSON API. Uploaded
files are base64-encoded by the browser, decoded here into temp files that
preserve the original extension (so detection works), run through the same
`extract()` pipeline the CLI uses, and returned as `Document.to_dict()`. The
server is offline by design: it binds to 127.0.0.1 only, never the network, and
is shut down by an explicit POST /api/shutdown so the page can stop it cleanly.
"""

import base64
import json
import os
import platform
import sys
import tempfile
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from . import ocr
from .backends.base import Options
from .core import capabilities, extract

# Reject oversized bodies before we ever buffer them into memory.
MAX_BODY = 200 * 1024 * 1024  # ~200 MB

# Where the static single-page app lives (sibling worker owns these files).
_WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

# Path -> (filesystem name, content-type) for the static assets we serve.
_STATIC = {
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}

_PLACEHOLDER_HTML = (
    "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
    "<title>omni-extract</title></head><body>"
    "<h1>omni-extract</h1>"
    "<p>The UI assets are not built yet. The API is live at "
    "<code>/api/capabilities</code> and <code>/api/extract</code>.</p>"
    "</body></html>"
)


def _platform() -> str:
    s = sys.platform
    if s.startswith("win"):
        return "windows"
    if s.startswith("linux"):
        return "linux"
    if s == "darwin":
        return "darwin"
    return platform.system().lower() or s


def _tesseract_langs() -> int:
    try:
        return len(ocr.languages())
    except Exception:
        return 0


class _Handler(BaseHTTPRequestHandler):
    server_version = "omni-extract"
    protocol_version = "HTTP/1.1"

    # --- quiet console -----------------------------------------------------
    def log_message(self, *args, **kwargs):  # noqa: D401 - silence stdlib logging
        pass

    # --- small response helpers -------------------------------------------
    def _send_json(self, obj, status: int = HTTPStatus.OK):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, body: bytes, content_type: str,
                    status: int = HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_error_json(self, status: int, message: str):
        self._send_json({"error": message}, status)

    def _send_file(self, fs_name: str, content_type: str):
        full = os.path.join(_WEB_DIR, fs_name)
        try:
            with open(full, "rb") as f:
                body = f.read()
        except OSError:
            self._send_error_json(HTTPStatus.NOT_FOUND, "not found")
            return
        self._send_bytes(body, content_type)

    # --- routing -----------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._serve_index()
        elif path in _STATIC:
            fs_name, ctype = _STATIC[path]
            self._send_file(fs_name, ctype)
        elif path == "/api/capabilities":
            self._capabilities()
        else:
            self._send_error_json(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/extract":
            self._extract()
        elif path == "/api/shutdown":
            self._shutdown()
        else:
            self._send_error_json(HTTPStatus.NOT_FOUND, "not found")

    # --- endpoints ---------------------------------------------------------
    def _serve_index(self):
        full = os.path.join(_WEB_DIR, "index.html")
        try:
            with open(full, "rb") as f:
                body = f.read()
        except OSError:
            body = _PLACEHOLDER_HTML.encode("utf-8")
        self._send_bytes(body, "text/html; charset=utf-8")

    def _capabilities(self):
        backends = [
            {"name": name, "kinds": list(kinds), "available": bool(ok),
             "hint": hint}
            for name, kinds, ok, hint in capabilities()
        ]
        self._send_json({
            "backends": backends,
            "platform": _platform(),
            "tesseract_langs": _tesseract_langs(),
        })

    def _read_body(self) -> Optional[bytes]:
        """Return the request body, or None after sending a 400."""
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._send_error_json(HTTPStatus.BAD_REQUEST, "bad Content-Length")
            return None
        if length < 0:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "bad Content-Length")
            return None
        if length > MAX_BODY:
            self._send_error_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                                  "request too large")
            return None
        return self.rfile.read(length) if length else b""

    def _extract(self):
        body = self._read_body()
        if body is None:
            return
        try:
            req = json.loads(body.decode("utf-8"))
            if not isinstance(req, dict):
                raise ValueError("expected a JSON object")
            files = req.get("files", [])
            if not isinstance(files, list):
                raise ValueError("'files' must be a list")
        except (ValueError, UnicodeDecodeError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST,
                                  f"malformed JSON: {exc}")
            return

        opts_in = req.get("options") or {}
        if not isinstance(opts_in, dict):
            opts_in = {}
        try:
            ocr_psm = int(opts_in.get("ocr_psm", 3))
        except (TypeError, ValueError):
            ocr_psm = 3
        ocr_lang = str(opts_in.get("ocr_lang", "eng")) or "eng"
        opts = Options(ocr_lang=ocr_lang, ocr_psm=ocr_psm)

        documents = []
        tmp_paths = []
        try:
            for entry in files:
                if not isinstance(entry, dict):
                    self._send_error_json(HTTPStatus.BAD_REQUEST,
                                          "each file must be an object")
                    return
                name = str(entry.get("name", "") or "upload")
                data_b64 = entry.get("data_b64", "")
                try:
                    raw = base64.b64decode(data_b64, validate=False)
                except Exception:
                    self._send_error_json(
                        HTTPStatus.BAD_REQUEST,
                        f"bad base64 for {name!r}")
                    return
                ext = os.path.splitext(name)[1]  # keep original extension
                with tempfile.NamedTemporaryFile(
                        prefix="omni-web-", suffix=ext, delete=False) as tf:
                    tf.write(raw)
                    tmp_path = tf.name
                tmp_paths.append(tmp_path)
                doc = extract(tmp_path, opts)
                d = doc.to_dict()
                d["path"] = name  # show the user's name, not the temp path
                documents.append(d)
        finally:
            for p in tmp_paths:
                try:
                    os.unlink(p)
                except OSError:
                    pass

        self._send_json({"documents": documents})

    def _shutdown(self):
        self._send_json({"ok": True})
        # Shut down from a background thread so this response flushes first;
        # server.shutdown() blocks until serve_forever() returns.
        threading.Thread(target=self.server.shutdown, daemon=True).start()


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(host: str = "127.0.0.1", port: int = 0,
          open_browser: bool = True) -> str:
    """Run the local UI server until POST /api/shutdown; return its URL.

    `port=0` picks an ephemeral port. Binds to loopback only.
    """
    httpd = _Server((host, port), _Handler)
    actual_port = httpd.server_address[1]
    url = f"http://{host}:{actual_port}/"
    print(f"omni-extract UI: {url}")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
    return url


def _selftest() -> int:
    """Start the server on a thread, exercise the API, then shut it down."""
    import io
    import re
    import urllib.request

    # `serve()` announces its URL on stdout *before* blocking in
    # serve_forever(); capture that to learn the ephemeral port.
    buf = io.StringIO()
    real_stdout = sys.stdout

    def run():
        try:
            sys.stdout = buf
            serve(host="127.0.0.1", port=0, open_browser=False)
        finally:
            sys.stdout = real_stdout

    t = threading.Thread(target=run, daemon=True)
    t.start()

    url = None
    for _ in range(500):
        m = re.search(r"http://127\.0\.0\.1:\d+/", buf.getvalue())
        if m:
            url = m.group(0)
            break
        threading.Event().wait(0.02)
    if not url:
        sys.stdout = real_stdout
        print("selftest FAILED: server did not start")
        return 1

    with urllib.request.urlopen(url + "api/capabilities", timeout=10) as resp:
        assert resp.status == 200, f"capabilities status {resp.status}"
        data = json.loads(resp.read().decode("utf-8"))
    assert "backends" in data, "capabilities JSON missing 'backends'"

    req = urllib.request.Request(
        url + "api/shutdown", data=b"{}", method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200, f"shutdown status {resp.status}"
        assert json.loads(resp.read().decode("utf-8")).get("ok") is True

    t.join(timeout=10)
    sys.stdout = real_stdout
    print("selftest ok")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(_selftest())
    serve()
