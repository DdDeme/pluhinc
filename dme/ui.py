"""Shared drawing helpers plus the Screen and MenuScreen building blocks."""
from PIL import Image, ImageFont

from . import artwork, theme

W = H = 128
ROW_H = 13
VISIBLE = 7  # menu rows that fit under the header

_DEJAVU = "/usr/share/fonts/truetype/dejavu/"


def _font(size, bold=False):
    name = "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf"
    try:
        return ImageFont.truetype(_DEJAVU + name, size)
    except OSError:
        try:
            return ImageFont.load_default(size)
        except TypeError:  # very old Pillow
            return ImageFont.load_default()


FONT = _font(10)
FONT_BOLD = _font(11, True)
FONT_SMALL = _font(9)

_background_on = True


def set_background(enabled):
    """Turn the faded photo behind every screen on or off."""
    global _background_on
    _background_on = bool(enabled)


def canvas():
    """A fresh 128x128 image to draw a screen on: the faded photo if enabled
    (and a photo exists), otherwise the theme's flat background colour."""
    if _background_on:
        image = artwork.faded()
        if image is not None:
            return image.copy()
    return Image.new("RGB", (W, H), theme.current()["bg"])


def clip(d, text, font, max_width):
    """Shorten text with '..' so it fits in max_width pixels."""
    if d.textlength(text, font=font) <= max_width:
        return text
    while text and d.textlength(text + "..", font=font) > max_width:
        text = text[:-1]
    return text + ".."


def wrap(d, text, font, max_width):
    """Greedy word wrap; over-long words are split."""
    lines, line = [], ""
    for word in text.split():
        while d.textlength(word, font=font) > max_width and len(word) > 1:
            cut = len(word)
            while cut > 1 and d.textlength(word[:cut], font=font) > max_width:
                cut -= 1
            if line:
                lines.append(line)
                line = ""
            lines.append(word[:cut])
            word = word[cut:]
        trial = (line + " " + word).strip()
        if d.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def header(d, title, right=None):
    """Draw the title bar; returns the y where content can start."""
    t = theme.current()
    d.rectangle([0, 0, W - 1, 14], fill=t["accent"])
    d.text((4, 1), title, font=FONT_BOLD, fill=t["bg"])
    if right:
        w = d.textlength(right, font=FONT_SMALL)
        d.text((W - 4 - w, 3), right, font=FONT_SMALL, fill=t["bg"])
    return 17


def footer(d, text):
    t = theme.current()
    d.text((4, H - 11), clip(d, text, FONT_SMALL, W - 8), font=FONT_SMALL, fill=t["dim"])


def kv(d, y, key, value, warn=False):
    """One 'KEY ........ value' row."""
    t = theme.current()
    d.text((4, y), key, font=FONT, fill=t["dim"])
    value = clip(d, value, FONT, W - 8 - 30)
    w = d.textlength(value, font=FONT)
    d.text((W - 4 - w, y), value, font=FONT, fill=t["warn"] if warn else t["fg"])


def bar(d, x, y, w, h, frac, warn_at=0.8):
    t = theme.current()
    frac = max(0.0, min(1.0, frac))
    d.rectangle([x, y, x + w - 1, y + h - 1], outline=t["dim"])
    fill_w = int((w - 2) * frac)
    if fill_w > 0:
        color = t["warn"] if frac >= warn_at else t["accent"]
        d.rectangle([x + 1, y + 1, x + fill_w, y + h - 2], fill=color)


class Screen:
    """Base class. Push instances onto the App's stack."""

    tick = None  # seconds between automatic redraws; None = redraw only on input
    use_background = True  # False = flat colour (e.g. games that need a clean playfield)
    right_is_down = True   # DOWN is the I2S LRCLK pin: RIGHT scrolls down instead. Games turn this off.

    def on_enter(self, app):
        pass

    def on_exit(self, app):
        pass

    def on_button(self, app, button):
        """Return True if the button was used; otherwise KEY3 goes back."""
        return False

    def full_image(self, app):
        """Return a complete 128x128 PIL Image to show as-is (skips draw()).
        Default None means: build a themed canvas and call draw() on it."""
        return None

    def draw(self, d, app):
        raise NotImplementedError


class MenuScreen(Screen):
    """A scrolling list. items = [(label, action)], action(app) runs on PRESS/RIGHT."""

    def __init__(self, title, items, footer_text="UP=up R=dn  K3 back"):
        self.title = title
        self.items = items
        self.footer_text = footer_text
        self.index = 0
        self.top = 0

    def on_button(self, app, button):
        count = len(self.items)
        if not count:
            return False
        if button == "UP":
            self.index = (self.index - 1) % count
        elif button == "DOWN":
            self.index = (self.index + 1) % count
        elif button in ("PRESS", "RIGHT"):
            self.items[self.index][1](app)
            return True
        else:
            return False
        if self.index < self.top:
            self.top = self.index
        elif self.index >= self.top + VISIBLE:
            self.top = self.index - VISIBLE + 1
        return True

    def draw(self, d, app):
        t = theme.current()
        y = header(d, self.title)
        for i in range(self.top, min(self.top + VISIBLE, len(self.items))):
            label = clip(d, self.items[i][0], FONT, W - 20)
            if i == self.index:
                d.rectangle([0, y, W - 1, y + ROW_H - 1], fill=t["accent"])
                d.text((6, y + 1), label, font=FONT, fill=t["bg"])
            else:
                d.text((6, y + 1), label, font=FONT, fill=t["fg"])
            y += ROW_H
        if self.top > 0:
            d.polygon([(W - 10, 25), (W - 4, 25), (W - 7, 20)], fill=t["dim"])
        if self.top + VISIBLE < len(self.items):
            d.polygon([(W - 10, 103), (W - 4, 103), (W - 7, 108)], fill=t["dim"])
        footer(d, self.footer_text)
