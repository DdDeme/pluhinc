"""Full-screen photo viewer, pushed automatically when a new photo lands in
~/dme_inbox (see inbox.py). Only KEY3 (back) closes it, so a stray or stuck
button can't dismiss it."""
import logging

from PIL import Image

from . import ui

log = logging.getLogger("dme")


class PhotoScreen(ui.Screen):
    tick = None

    def __init__(self, path):
        self.path = path
        self._img = self._load(path)

    def _load(self, path):
        try:
            img = Image.open(path).convert("RGB")
            img.thumbnail((ui.W, ui.H), Image.LANCZOS)
            canvas = Image.new("RGB", (ui.W, ui.H), (0, 0, 0))
            canvas.paste(img, ((ui.W - img.width) // 2, (ui.H - img.height) // 2))
            return canvas
        except Exception:
            log.exception("couldn't open photo %s", path)
            return None

    def on_button(self, app, button):
        # swallow everything except KEY3; the app handles KEY3 by going back
        return button != "KEY3"

    def full_image(self, app):
        return self._img

    def draw(self, d, app):
        # only reached if _img failed to load (full_image returned None)
        d.text((4, 4), "Couldn't open photo", font=ui.FONT, fill=(255, 90, 60))
