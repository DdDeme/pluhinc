"""Plays a video full-screen: ffmpeg decodes frames at 128x128 in a background
thread while mpv plays the audio track roughly in sync. Only KEY3 (back) stops it
and goes back, so a stray or stuck button can't end the video. Used automatically
for videos that land in ~/dme_inbox."""
import logging
import queue
import subprocess
import threading

from PIL import Image, ImageDraw

from . import bluetooth, ui

log = logging.getLogger("dme")

FPS = 12
FRAME_BYTES = ui.W * ui.H * 3


class VideoScreen(ui.Screen):
    tick = 1.0 / FPS

    def __init__(self, path):
        self.path = path
        self.done = False
        self._frame = None
        self._frames = queue.Queue(maxsize=4)
        self._ffmpeg = None
        self._audio = None
        self._thread = threading.Thread(target=self._decode, daemon=True)

    def on_enter(self, app):
        self._thread.start()
        try:
            self._audio = subprocess.Popen(
                ["mpv", "--no-video", "--really-quiet",
                 *bluetooth.audio_args(app.settings), self.path])
        except FileNotFoundError:
            log.warning("mpv not found - playing video without sound")

    def _decode(self):
        try:
            self._ffmpeg = subprocess.Popen(
                ["ffmpeg", "-loglevel", "error", "-i", self.path,
                 "-vf", f"scale={ui.W}:{ui.H},fps={FPS}",
                 "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                stdout=subprocess.PIPE,
            )
            while True:
                data = self._ffmpeg.stdout.read(FRAME_BYTES)
                if len(data) < FRAME_BYTES:
                    break
                try:
                    self._frames.put(data, timeout=1)
                except queue.Full:
                    pass
        except FileNotFoundError:
            log.exception("ffmpeg not installed - run setup.sh")
        finally:
            self.done = True

    def on_button(self, app, button):
        # swallow everything except KEY3; the app handles KEY3 by going back (on_exit stops playback)
        return button != "KEY3"

    def on_exit(self, app):
        self._stop()

    def _stop(self):
        if self._ffmpeg and self._ffmpeg.poll() is None:
            self._ffmpeg.terminate()
        if self._audio and self._audio.poll() is None:
            self._audio.terminate()

    def full_image(self, app):
        try:
            data = self._frames.get_nowait()
            self._frame = Image.frombytes("RGB", (ui.W, ui.H), data)
        except queue.Empty:
            pass
        if self._frame is None:
            return Image.new("RGB", (ui.W, ui.H), (0, 0, 0))
        if self.done and self._frames.empty():
            img = self._frame.copy()
            d = ImageDraw.Draw(img)
            msg = "END - press KEY3"
            w = d.textlength(msg, font=ui.FONT_SMALL)
            d.rectangle([0, ui.H - 12, ui.W, ui.H], fill=(0, 0, 0))
            d.text(((ui.W - w) / 2, ui.H - 10), msg, font=ui.FONT_SMALL, fill=(255, 255, 255))
            return img
        return self._frame

    def draw(self, d, app):
        pass  # unused: full_image() handles everything
