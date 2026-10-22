"""A few handheld utilities: flashlight, stopwatch, clock."""
import time

from PIL import Image

from . import theme, ui


class FlashlightScreen(ui.Screen):
    tick = None

    def full_image(self, app):
        return Image.new("RGB", (ui.W, ui.H), (255, 255, 255))

    def draw(self, d, app):
        pass  # unused: full_image() handles everything


class StopwatchScreen(ui.Screen):
    tick = 0.2

    def __init__(self):
        self.running = False
        self.elapsed = 0.0
        self._started_at = None

    def on_button(self, app, button):
        if button in ("PRESS", "RIGHT"):
            if self.running:
                self.elapsed += time.monotonic() - self._started_at
                self.running = False
            else:
                self._started_at = time.monotonic()
                self.running = True
            return True
        if button == "KEY2":
            self.elapsed = 0.0
            self.running = False
            return True
        return False

    def draw(self, d, app):
        t = theme.current()
        ui.header(d, "STOPWATCH")
        total = self.elapsed + (time.monotonic() - self._started_at if self.running else 0.0)
        m, s = divmod(total, 60)
        text = f"{int(m):02d}:{s:05.2f}"
        w = d.textlength(text, font=ui.FONT_BOLD)
        d.text(((ui.W - w) / 2, 50), text, font=ui.FONT_BOLD, fill=t["accent"])
        state = "running" if self.running else "stopped"
        ui.footer(d, f"[{state}] PRESS start/stop  K2 reset")


class ClockScreen(ui.Screen):
    tick = 1.0

    def draw(self, d, app):
        t = theme.current()
        ui.header(d, "CLOCK")
        now = time.localtime()
        text = time.strftime("%H:%M:%S", now)
        w = d.textlength(text, font=ui.FONT_BOLD)
        d.text(((ui.W - w) / 2, 48), text, font=ui.FONT_BOLD, fill=t["accent"])
        date = time.strftime("%a %d %b %Y", now)
        w2 = d.textlength(date, font=ui.FONT)
        d.text(((ui.W - w2) / 2, 66), date, font=ui.FONT, fill=t["dim"])
        ui.footer(d, "needs correct system time")


def tools_menu():
    return ui.MenuScreen("TOOLS", [
        ("Flashlight", lambda app: app.push(FlashlightScreen())),
        ("Stopwatch", lambda app: app.push(StopwatchScreen())),
        ("Clock", lambda app: app.push(ClockScreen())),
    ])
