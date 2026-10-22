"""Tiny HTTP endpoint so a phone can hand DME OS a photo or video.

Point an iPhone Shortcut (Share Sheet -> Shortcut -> "Get Contents of URL",
Method POST, Request Body = the shared file) at:

    http://<pi-ip-address>:8000/upload

Each upload is saved into ~/dme_inbox/ and DME OS immediately pops up a
full-screen viewer (photos) or starts playing it (videos); press any button
to dismiss/stop. Find the Pi's IP under Settings > WiFi, or with
`hostname -I` over SSH.
"""
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("dme")

PORT = 8000
INBOX_DIR = os.path.expanduser("~/dme_inbox")
MAX_BYTES = 25 * 1024 * 1024
EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/heic": ".heic",
    "image/heif": ".heic",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-m4v": ".m4v",
}


class _Handler(BaseHTTPRequestHandler):
    server_version = "DMEInbox/1.0"

    def log_message(self, fmt, *args):
        log.info("inbox: " + fmt, *args)

    def do_GET(self):
        body = b"DME OS photo inbox is up. POST an image to /upload."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/upload":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > MAX_BYTES:
            self.send_response(400)
            self.end_headers()
            return
        data = self.rfile.read(length)
        ctype = self.headers.get("Content-Type", "").split(";")[0].strip()
        ext = EXTENSIONS.get(ctype, ".jpg")
        os.makedirs(INBOX_DIR, exist_ok=True)
        name = f"photo_{int(time.time())}{ext}"
        path = os.path.join(INBOX_DIR, name)
        with open(path, "wb") as f:
            f.write(data)
        log.info("received photo %s (%d bytes)", name, len(data))
        on_photo = getattr(self.server, "on_photo", None)
        if on_photo:
            on_photo(path)
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
        log.info("photo inbox listening on :%d", self._server.server_port)

    def close(self):
        self._server.shutdown()
        self._server.server_close()
