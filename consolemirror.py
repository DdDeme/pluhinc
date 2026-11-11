#!/usr/bin/env python3
"""Mirror the Pi's boot console onto the LCD while it boots.

With no HDMI monitor attached the firmware leaves a blank/white framebuffer
behind, so this reads the active virtual console's text instead and draws the
raw startup output, with no status bar or other UI.

It stops by itself, leaving the LCD alone, when:
  * DME OS starts (dme-os.service and dme_os.py both stop this service first), or
  * a monitor or TV is plugged into the HDMI port.

Runs as dme-console.service (installed by setup.sh).
"""
import glob
import hashlib
import os
import re
import signal
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from dme import hal  # noqa: E402
from dme.settings import CONFIG_DIR  # noqa: E402

W = H = 128
FONT_SIZE = 5
ROW_H = 6
VIEW_H = H                               # raw console text fills the whole screen
TEXT_ROWS = VIEW_H // ROW_H              # ~21 lines of console text
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FRAMEBUFFER = "/dev/fb0"
FB_SYSFS = "/sys/class/graphics/fb0"
POLL_SECONDS = 0.5
FB_RETRY_SECONDS = 5.0
HDMI_HITS = 3                            # ~1.5 s of "connected" before we believe it


def load_font():
    try:
        return ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except OSError:
        try:
            return ImageFont.load_default(FONT_SIZE)
        except TypeError:
            return ImageFont.load_default()


def read_console():
    """The active console's text as a list of lines (blank lines at the bottom
    removed), or None if it can't be read.

    /dev/vcsN is a flat screen buffer with no newline characters, so the screen
    width has to come from the /dev/vcsaN header (rows, cols, cursor x, cursor y).
    """
    try:
        with open("/sys/class/tty/tty0/active") as f:
            active = f.read().strip()
    except OSError:
        active = "tty1"
    index = active[3:] if active.startswith("tty") else "1"
    rows, cols = 24, 80
    try:
        with open("/dev/vcsa" + index, "rb") as f:
            header = f.read(4)
        if len(header) == 4 and header[0] and header[1]:
            rows, cols = header[0], header[1]
    except OSError:
        pass
    try:
        with open("/dev/vcs" + index, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    text = raw.decode("utf-8", errors="replace").replace("\r", "").replace("\x00", " ")
    lines = [text[i:i + cols].strip() for i in range(0, min(len(text), rows * cols), cols)]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def hdmi_connected():
    """True while a monitor/TV is plugged into the HDMI port."""
    for path in glob.glob("/sys/class/drm/card*-HDMI-A-*/status"):
        try:
            with open(path) as f:
                if f.read().strip() == "connected":
                    return True
        except OSError:
            pass
    return False


def fb_info():
    """(width, height, bits per pixel, bytes per row) of the HDMI framebuffer."""
    with open(os.path.join(FB_SYSFS, "virtual_size")) as f:
        parts = re.split(r"[, ]+", f.read().strip())
    width, height = int(parts[0]), int(parts[1])
    with open(os.path.join(FB_SYSFS, "bits_per_pixel")) as f:
        bpp = int(f.read().strip())
    try:
        with open(os.path.join(FB_SYSFS, "stride")) as f:
            stride = int(f.read().strip())
    except OSError:
        stride = width * bpp // 8
    return width, height, bpp, stride


def decode_framebuffer(data, width, height, bpp, stride):
    """Turn the raw /dev/fb0 bytes into a PIL image."""
    if bpp == 32:      # little-endian XRGB8888, the usual Raspberry Pi format
        image = Image.frombuffer("RGBA", (width, height), data, "raw", "BGRA", stride, 1)
    elif bpp == 16:    # RGB565
        image = Image.frombuffer("RGB", (width, height), data, "raw", "BGR;16", stride, 1)
    elif bpp == 24:
        image = Image.frombuffer("RGB", (width, height), data, "raw", "BGR", stride, 1)
    else:
        raise ValueError(f"unsupported framebuffer depth: {bpp} bpp")
    return image.convert("RGB")


class Framebuffer:
    """Reads the HDMI framebuffer, following resolution changes."""

    def __init__(self):
        self._image = None
        self._signature = None
        self._retry_at = 0.0

    def capture(self, now):
        """(signature, PIL image) of what HDMI shows, or None if unavailable.
        The same image object is returned while the screen hasn't changed."""
        if now < self._retry_at:
            return None
        try:
            width, height, bpp, stride = fb_info()
            # /dev/fb0 is a character device (and doesn't support seeking), so
            # open it fresh and read the exact frame size each time.
            with open(FRAMEBUFFER, "rb") as f:
                data = f.read(stride * height)
            if len(data) < stride * height:
                raise OSError(f"short read from {FRAMEBUFFER}")
        except (OSError, ValueError):
            self._retry_at = now + FB_RETRY_SECONDS
            return None

        signature = hashlib.blake2b(data, digest_size=8).digest()
        if signature != self._signature or self._image is None:
            try:
                self._image = decode_framebuffer(data, width, height, bpp, stride)
            except ValueError:
                self._retry_at = now + FB_RETRY_SECONDS
                return None
            self._signature = signature
        return self._signature, self._image


def fit_screen(image):
    """Shrink the HDMI picture to fit the LCD."""
    width, height = image.size
    scale = min(W / width, VIEW_H / height)
    size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return image.resize(size, Image.BOX)


def center(image):
    """Centre a picture on a black square."""
    full = Image.new("RGB", (W, H), (0, 0, 0))
    full.paste(image, ((W - image.width) // 2, (H - image.height) // 2))
    return full


def render_text(font, cols, lines):
    """The raw text console: the last lines of the active virtual console."""
    image = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(image)
    y = 0
    for line in lines[-TEXT_ROWS:]:
        d.text((0, y), line[:cols], font=font, fill=(210, 210, 210))
        y += ROW_H
    return image


def main():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.chdir(CONFIG_DIR)  # lgpio drops small notification files in the working directory

    stopping = []
    signal.signal(signal.SIGTERM, lambda *_: stopping.append(True))
    signal.signal(signal.SIGINT, lambda *_: stopping.append(True))

    display, error = None, None
    for _ in range(30):  # early in boot the SPI device may not exist yet
        if stopping:
            return
        try:
            display = hal.Display()
            break
        except Exception as exc:
            error = exc
            time.sleep(1)
    if display is None:
        sys.exit(f"LCD not available: {error!r}")

    font = load_font()
    cols = max(10, int(W / font.getlength("M")))
    fb = Framebuffer()
    hdmi_hits = 0
    last_key = None

    while not stopping:
        now = time.monotonic()

        # a monitor was plugged in: it shows the console now, so the LCD can stop mirroring
        hdmi = hdmi_connected()
        hdmi_hits = hdmi_hits + 1 if hdmi else 0
        if hdmi_hits >= HDMI_HITS:
            try:
                from dme import artwork
                photo = artwork.logo()
            except Exception:
                photo = None
            if photo is None:
                photo = render_text(font, cols, ["HDMI connected"])
            display.show(center(photo))
            return

        # With no monitor attached the firmware's simple framebuffer is often just
        # a white screen; the text console is the reliable source during boot.
        shot = fb.capture(now) if hdmi else None
        if shot is not None:
            signature, screen = shot
            full = center(fit_screen(screen))
            key = signature
        else:
            lines = read_console()
            if lines is None:
                lines = ["can't read the console",
                         "(is the user in the 'tty' group?)"]
            full = render_text(font, cols, lines)
            key = tuple(lines[-TEXT_ROWS:])

        if key != last_key:
            display.show(full)
            last_key = key
        time.sleep(POLL_SECONDS)
    # stopped by SIGTERM (DME OS is starting): leave the last frame - DME draws over it right away


if __name__ == "__main__":
    main()
