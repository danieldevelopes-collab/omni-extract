"""Email: .eml (single message) and .mbox (many) via the stdlib `email`
package. Headers we care about plus every text/plain and text/html body part
(HTML is run through the markup stripper)."""

import email
import mailbox
from email import policy

from ..document import Document
from .base import Backend, Options
from .markup import _Text

_HEADERS = ("From", "To", "Cc", "Subject", "Date")


def _strip_html(html: str) -> str:
    p = _Text()
    try:
        p.feed(html)
    except Exception:
        return html
    return p.text()


def _message_text(msg) -> str:
    parts = []
    for h in _HEADERS:
        v = msg.get(h)
        if v:
            parts.append(f"{h}: {v}")
    parts.append("")
    try:
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
                    parts.append(str(part.get_content()))
                elif ct == "text/html":
                    parts.append(_strip_html(str(part.get_content())))
        else:
            content = str(msg.get_content())
            if msg.get_content_type() == "text/html":
                content = _strip_html(content)
            parts.append(content)
    except Exception as exc:
        parts.append(f"[body decode error: {exc}]")
    return "\n".join(parts).strip()


class EmailBackend(Backend):
    name = "email"
    kinds = ("email", "mbox")

    def extract(self, path: str, kind: str, opts: Options) -> Document:
        doc = Document(path=path, kind=kind, backend=self.name)
        if kind == "mbox":
            try:
                box = mailbox.mbox(path)
            except Exception as exc:
                return Document.failed(path, f"mbox open failed: {exc}", kind)
            for i, msg in enumerate(box, 1):
                doc.add_page(_message_text(msg), method="email",
                             label=f"message {i}")
            return doc
        try:
            with open(path, "rb") as fh:
                msg = email.message_from_binary_file(fh, policy=policy.default)
        except Exception as exc:
            return Document.failed(path, f"eml parse failed: {exc}", kind)
        doc.add_page(_message_text(msg), method="email")
        return doc
