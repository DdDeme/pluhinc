"""Tiny HTTP endpoint so a phone can hand DME OS a photo or video.

Point an iPhone Shortcut (Share Sheet -> Shortcut -> "Get Contents of URL",
Method POST, Request Body = the shared file) at:

    http://<pi-ip-address>:8000/upload

Videos work the same way as photos: MP4, MOV, M4V, 3GP, WebM, MKV and AVI are
accepted. Shortcuts sometimes uploads a file as application/octet-stream, so
the file signature is used when the Content-Type or filename is not helpful.

Each upload is saved into ~/dme_inbox/ and DME OS immediately pops up a
full-screen viewer (photos) or starts playing it (videos); press any button
to dismiss/stop. Find the Pi's IP under Settings > WiFi, or with
`hostname -I` over SSH.
"""
import logging
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

log = logging.getLogger("dme")

PORT = 8000
INBOX_DIR = os.path.expanduser("~/dme_inbox")
MAX_BYTES = 200 * 1024 * 1024       # videos from a phone can be much larger than photos
CHUNK = 64 * 1024
HEAD_BYTES = 64

# Content-Type values Shortcuts/iOS commonly sends. application/octet-stream
# deliberately has no entry: the file signature decides for those.
EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/heic": ".heic",
    "image/heif": ".heic",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-m4v": ".m4v",
    "video/3gpp": ".3gp",
    "video/3gpp2": ".3g2",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
    "video/x-msvideo": ".avi",
    "application/mp4": ".mp4",
}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".3gp", ".3g2", ".webm", ".mkv", ".avi"}
IMAGE_EXTS = {".jpg", ".png", ".heic", ".gif", ".webp"}
ALIASES = {".jpeg": ".jpg", ".jpe": ".jpg", ".heif": ".heic"}
KNOWN_EXTS = VIDEO_EXTS | IMAGE_EXTS

_FILENAME = re.compile(r'filename\*?=(?:"([^"]+)"|([^;]+))', re.IGNORECASE)


def sniff_extension(head):
    """Guess an extension from the first bytes, not from the HTTP headers."""
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if head.startswith(b"RIFF") and len(head) >= 12:
        kind = head[8:12]
        if kind == b"AVI ":
            return ".avi"
        if kind == b"WEBP":
            return ".webp"
    if head.startswith(b"\x1aE\xdf\xa3"):       # Matroska / WebM
        return ".webm"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand == b"qt  ":
            return ".mov"
        if brand in (b"M4V ", b"M4VH", b"M4VP"):
            return ".m4v"
        if brand.startswith(b"3gp"):
            return ".3gp"
        if brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"):
            return ".heic"
        return ".mp4"
    return None


def _header_extension(headers, query):
    """Use a filename from Content-Disposition or ?filename=..., if present."""
    raw = ""
    match = _FILENAME.search(headers.get("Content-Disposition", ""))
    if match:
        raw = match.group(1) or match.group(2) or ""
    else:
        values = query.get("filename") or query.get("name")
        if values:
            raw = values[0]
    raw = unquote(raw.strip().strip('"'))
    if raw.lower().startswith("utf-8''"):
        raw = raw[7:]
    raw = os.path.basename(raw.replace("\\", "/"))
    ext = os.path.splitext(raw)[1].lower()
    ext = ALIASES.get(ext, ext)
    return ext if ext in KNOWN_EXTS else None


class _Handler(BaseHTTPRequestHandler):
    server_version = "DMEInbox/1.1"

    def log_message(self, fmt, *args):
        log.info("inbox: " + fmt, *args)

    def _error(self, code, message):
        body = (message + "\n").encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        body = b"DME OS photo/video inbox is up. POST an image or video to /upload."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        parts = urlsplit(self.path)
        if parts.path != "/upload":
            self._error(404, "not found")
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if length <= 0:
            self._error(411, "Content-Length is required")
            return
        if length > MAX_BYTES:
            self.close_connection = True
            self._error(413, f"file too large (max {MAX_BYTES // (1024 * 1024)} MB)")
            return

        # Read just the header bytes first: the file signature is more reliable
        # than Shortcuts' Content-Type, which is often application/octet-stream.
        head = self.rfile.read(min(HEAD_BYTES, length))
        if not head:
            self._error(400, "empty upload")
            return

        ctype = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        query = parse_qs(parts.query)
        ext = (sniff_extension(head)
               or _header_extension(self.headers, query)
               or EXTENSIONS.get(ctype))
        if ext is None:
            self.close_connection = True
            self._error(415, "unsupported file type - use an image or a video")
            return

        os.makedirs(INBOX_DIR, exist_ok=True)
        stamp = time.time_ns()
        path = os.path.join(INBOX_DIR, f"photo_{stamp}{ext}")
        try:
            with open(path, "wb") as f:
                f.write(head)
                remaining = length - len(head)
                while remaining > 0:
                    chunk = self.rfile.read(min(CHUNK, remaining))
                    if not chunk:
                        raise ConnectionError("upload ended early")
                    f.write(chunk)
                    remaining -= len(chunk)
        except Exception:
            log.exception("inbox: failed to save upload")
            try:
                os.unlink(path)
            except OSError:
                pass
            self._error(500, "could not save upload")
            return

        log.info("received media %s (%d bytes)", os.path.basename(path), length)
        on_media = getattr(self.server, "on_photo", None)
        if on_media:
            on_media(path)
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


class Inbox:
    """Runs the upload server in a background thread. on_photo(path) fires per upload."""

    def __init__(self, on_photo, port=PORT):
        self._server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
        self._server.on_photo = on_photo
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()
        log.info("photo/video inbox listening on :%d", self._server.server_port)

    def close(self):
        self._server.shutdown()
        self._server.server_close()
