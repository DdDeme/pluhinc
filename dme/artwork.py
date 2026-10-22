"""The boot photo and the faded menu background, both built from dme/assets/boot.png.

Drop any photo there (png/jpg, any size). Portrait photos are cropped to a square
(starting a little below the top so a face stays in frame) and shrunk to 128x128.
The shrunken copy is cached in ~/.config/dme_os so later boots don't re-decode the big file.
"""
import logging
import os

from PIL import Image

from . import theme
from .settings import CONFIG_DIR

log = logging.getLogger("dme")

ASSET_DIRS = (
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"),                 # dme/assets
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"),  # <repo>/assets
)
ASSET_DIR = ASSET_DIRS[0]
NAMES = ("boot.png", "boot.jpg", "boot.jpeg", "bootlogo.png")
SIZE = 128
FOCUS_Y = 0.083      # portrait photos: where the square crop starts, as a fraction of the height
BG_STRENGTH = 0.20   # how visible the faded background is (0 = flat colour, 1 = full photo)

_logo = None
_loaded = False
_faded_cache = {}


def _find_source():
    for folder in ASSET_DIRS:
        for name in NAMES:
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                return path
    return None


def _square(img):
    w, h = img.size
    if w >= h:  # landscape or square: centre crop
        x0 = (w - h) // 2
        box = (x0, 0, x0 + h, h)
    else:       # portrait: full width, starting FOCUS_Y of the way down
        y0 = min(int(round(FOCUS_Y * h)), h - w)
        box = (0, y0, w, y0 + w)
    return img.crop(box).resize((SIZE, SIZE), Image.LANCZOS)


def logo():
    """The 128x128 full-brightness photo, or None if no image has been added yet."""
    global _logo, _loaded
    if _loaded:
        return _logo
    _loaded = True
    source = _find_source()
    if source is None:
        log.warning("no boot image found - put one at %s", os.path.join(ASSET_DIR, NAMES[0]))
        return None
    cached = os.path.join(CONFIG_DIR, f"boot_{SIZE}_{FOCUS_Y}.png")
    try:
        if os.path.isfile(cached) and os.path.getmtime(cached) >= os.path.getmtime(source):
            _logo = Image.open(cached).convert("RGB")
        else:
            _logo = _square(Image.open(source).convert("RGB"))
            try:
                os.makedirs(CONFIG_DIR, exist_ok=True)
                _logo.save(cached)
            except OSError:
                log.warning("couldn't write the boot image cache")
    except Exception:
        log.exception("couldn't load the boot image")
        _logo = None
    return _logo


def faded(strength=BG_STRENGTH):
    """The photo blended into the current theme's background colour (None without a photo)."""
    photo = logo()
    if photo is None:
        return None
    key = (theme.current_name(), strength)
    image = _faded_cache.get(key)
    if image is None:
        flat = Image.new("RGB", (SIZE, SIZE), theme.current()["bg"])
        image = Image.blend(flat, photo, strength)
        _faded_cache[key] = image
    return image
