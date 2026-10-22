"""Boot splash: the photo fades in from black, holds, then dissolves into the faded
menu background so the main menu appears without a jump.

Needs a photo at dme/assets/boot.png (see artwork.py). Without one the splash is skipped.
"""
import logging
import time

from PIL import Image

from . import artwork, theme, ui

log = logging.getLogger("dme")

FADE_IN_SECONDS = 0.6
HOLD_SECONDS = 1.5
FADE_OUT_SECONDS = 1.0
STEPS = 12


def _menu_look(use_background):
    """What the main menu will look like behind its text."""
    if use_background:
        image = artwork.faded()
        if image is not None:
            return image
    return Image.new("RGB", (ui.W, ui.H), theme.current()["bg"])


def play(display, use_background=True):
    """Blocking boot animation. Safe to call even if the photo is missing."""
    photo = artwork.logo()
    if photo is None:
        log.warning("boot splash skipped (no photo)")
        return

    black = Image.new("RGB", (ui.W, ui.H), (0, 0, 0))
    for step in range(1, STEPS + 1):
        display.show(Image.blend(black, photo, step / STEPS))
        time.sleep(FADE_IN_SECONDS / STEPS)

    time.sleep(HOLD_SECONDS)

    target = _menu_look(use_background)
    for step in range(1, STEPS + 1):
        display.show(Image.blend(photo, target, step / STEPS))
        time.sleep(FADE_OUT_SECONDS / STEPS)
