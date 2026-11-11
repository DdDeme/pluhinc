"""The App: owns the screen stack and the main loop."""
import logging
import queue
import subprocess
import time

from PIL import Image, ImageDraw

from . import music, theme, ui

log = logging.getLogger("dme")

VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".3gp", ".3g2", ".webm", ".avi", ".mkv")


class App:
    def __init__(self, display, inp, settings, photo_queue=None):
        self.display = display
        self.input = inp
        self.settings = settings
        self.stack = []
        self.dirty = True
        self.running = True
        self.skip_clear = False  # set when powering off so the message stays up
        self._last_draw = 0.0
        self.photo_queue = photo_queue  # new photos from the HTTP inbox land here

    # ---- screen stack -------------------------------------------------
    @property
    def screen(self):
        return self.stack[-1]

    def push(self, screen):
        self.stack.append(screen)
        screen.on_enter(self)
        self.dirty = True

    def pop(self):
        """Go back one screen. The root screen stays."""
        if len(self.stack) > 1:
            self.stack.pop().on_exit(self)
            self.dirty = True

    def quit(self):
        self.running = False

    # ---- main loop ----------------------------------------------------
    def run(self):
        while self.running:
            if self.input.error is not None:
                raise RuntimeError(f"button thread died: {self.input.error!r}")
            if self.photo_queue is not None:
                try:
                    while True:
                        path = self.photo_queue.get_nowait()
                        if path.lower().endswith(VIDEO_EXTS):
                            from . import video
                            self.push(video.VideoScreen(path))
                        else:
                            from . import photos
                            self.push(photos.PhotoScreen(path))
                except queue.Empty:
                    pass
            music.update()  # starts the next track when one finishes
            for button in self._wait_for_events(timeout=0.05):
                if button == "RIGHT" and self.screen.right_is_down:
                    button = "DOWN"  # DOWN is the I2S LRCLK pin: RIGHT scrolls down in menus and lists
                consumed = self.screen.on_button(self, button)
                if not consumed and button == "KEY3":
                    self.pop()
                self.dirty = True
            tick = self.screen.tick
            if tick and time.monotonic() - self._last_draw >= tick:
                self.dirty = True
            if self.dirty and self.running:
                self.render()

    def _wait_for_events(self, timeout):
        """Block briefly for one event, then grab everything else already queued."""
        events = []
        try:
            events.append(self.input.events.get(timeout=timeout))
            while True:
                events.append(self.input.events.get_nowait())
        except queue.Empty:
            pass
        return events

    def render(self):
        custom = self.screen.full_image(self)
        if custom is not None:
            image = custom
        else:
            if self.screen.use_background:
                image = ui.canvas()
            else:
                image = Image.new("RGB", (ui.W, ui.H), theme.current()["bg"])
            self.screen.draw(ImageDraw.Draw(image), self)
        self.display.show(image)
        self._last_draw = time.monotonic()
        self.dirty = False

    # ---- helpers for screens ------------------------------------------
    def message(self, text, color="fg"):
        """Show centred text right now (used for 'Shutting down...' and crashes)."""
        t = theme.current()
        image = Image.new("RGB", (ui.W, ui.H), t["bg"])
        d = ImageDraw.Draw(image)
        lines = ui.wrap(d, text, ui.FONT, ui.W - 12)[:8]
        y = (ui.H - len(lines) * ui.ROW_H) // 2
        for line in lines:
            w = d.textlength(line, font=ui.FONT)
            d.text(((ui.W - w) / 2, y), line, font=ui.FONT, fill=t[color])
            y += ui.ROW_H
        self.display.show(image)

    def power(self, action):
        """action is 'poweroff' or 'reboot'."""
        self.message("Shutting down..." if action == "poweroff" else "Rebooting...")
        log.info("power action: %s", action)
        subprocess.Popen(["sudo", "systemctl", action])
        self.skip_clear = True
        self.running = False

    def show_crash(self, summary):
        try:
            self.message("CRASH: " + summary, color="warn")
            time.sleep(4)
        except Exception:
            pass

    def close(self):
        music.stop_all()  # don't leave mpv playing after DME exits or crashes
        if not self.skip_clear:
            self.display.close()
        self.input.close()
