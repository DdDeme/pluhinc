"""Simple file browser rooted at ~/dme_files."""
import logging
import os

from . import theme, ui

log = logging.getLogger("dme")
ROOT = os.path.expanduser("~/dme_files")


def _listing(path):
    try:
        entries = sorted(os.listdir(path))
    except OSError:
        entries = []
    dirs = [e for e in entries if os.path.isdir(os.path.join(path, e))]
    files = [e for e in entries if e not in dirs]
    return dirs, files


class FileInfoScreen(ui.Screen):
    def __init__(self, path):
        self.path = path
        try:
            self.size = os.path.getsize(path)
        except OSError:
            self.size = 0
        self.confirming = False

    def on_button(self, app, button):
        if self.confirming:
            if button in ("PRESS", "RIGHT"):
                try:
                    os.remove(self.path)
                except OSError:
                    log.exception("delete failed")
                app.pop()
            else:
                self.confirming = False
            return True
        if button in ("PRESS", "RIGHT"):
            self.confirming = True
            return True
        return False

    def draw(self, d, app):
        t = theme.current()
        y = ui.header(d, "FILE")
        d.text((4, y), ui.clip(d, os.path.basename(self.path), ui.FONT, ui.W - 8),
               font=ui.FONT, fill=t["fg"])
        y += 16
        d.text((4, y), f"{self.size / 1024:.1f} KB", font=ui.FONT, fill=t["dim"])
        y += 24
        if self.confirming:
            d.text((4, y), "PRESS=delete  K3=cancel", font=ui.FONT_SMALL, fill=t["warn"])
        else:
            ui.footer(d, "PRESS  delete")


class FilesScreen(ui.Screen):
    def __init__(self, path=None):
        self.path = path or ROOT
        os.makedirs(ROOT, exist_ok=True)
        self.index = 0
        self.top = 0
        self._refresh()

    def _refresh(self):
        dirs, files = _listing(self.path)
        self.items = [(".. (up)", None)] if self.path != ROOT else []
        self.items += [(f"/{d}", "dir") for d in dirs]
        self.items += [(f, "file") for f in files]

    def on_enter(self, app):
        self._refresh()

    def on_button(self, app, button):
        count = len(self.items)
        if button == "UP" and count:
            self.index = (self.index - 1) % count
        elif button == "DOWN" and count:
            self.index = (self.index + 1) % count
        elif button in ("PRESS", "RIGHT") and count:
            label, kind = self.items[self.index]
            if kind is None:
                app.pop()
            elif kind == "dir":
                app.push(FilesScreen(os.path.join(self.path, label[1:])))
            else:
                app.push(FileInfoScreen(os.path.join(self.path, label)))
        else:
            return False
        if self.index < self.top:
            self.top = self.index
        elif self.index >= self.top + ui.VISIBLE:
            self.top = self.index - ui.VISIBLE + 1
        return True

    def draw(self, d, app):
        t = theme.current()
        y = ui.header(d, "FILES", right=os.path.basename(self.path) or "/")
        if not self.items:
            d.text((4, y), "(empty)", font=ui.FONT, fill=t["dim"])
        for i in range(self.top, min(self.top + ui.VISIBLE, len(self.items))):
            label = ui.clip(d, self.items[i][0], ui.FONT, ui.W - 20)
            if i == self.index:
                d.rectangle([0, y, ui.W - 1, y + ui.ROW_H - 1], fill=t["accent"])
                d.text((6, y + 1), label, font=ui.FONT, fill=t["bg"])
            else:
                d.text((6, y + 1), label, font=ui.FONT, fill=t["fg"])
            y += ui.ROW_H
        ui.footer(d, "PRESS open  K3 back")
