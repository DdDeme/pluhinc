#!/usr/bin/env python3
"""Shows the boot photo on the LCD and exits, very early in boot.

The photo is the same one the in-app splash uses (dme/assets/boot.png, see
artwork.py). The ST7735 panel keeps whatever was last pushed to it in its own
memory, so the picture can stay up with no process holding it there while the
rest of the system finishes booting. See dme-bootlogo.service.

If the screen goes dark the moment this exits, the backlight pin was released
along with the process - tell me and we'll keep it alive instead.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from dme import artwork, hal  # noqa: E402
from dme.settings import CONFIG_DIR  # noqa: E402


def main():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.chdir(CONFIG_DIR)  # lgpio drops small notification files in the working directory
    image = artwork.logo()
    if image is None:
        sys.exit("no boot image found - put one at dme/assets/boot.png")
    display = hal.Display()
    display.show(image)
    # deliberately no display.close() - that would blank the screen again


if __name__ == "__main__":
    main()
