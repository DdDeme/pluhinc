"""Hardware layer for the Waveshare 1.44" LCD HAT (ST7735S, 128x128).

Display: uses Waveshare's own LCD_1in44 driver.
Input:   reads the joystick and the 3 keys with lgpio in a background thread and
         queues the presses, so a slow screen redraw can never swallow a press.
"""
import os
import queue
import sys
import threading
import time

W = H = 128

# BCM pin numbers of the HAT's joystick and keys
PINS = {
    "UP": 6,
    "DOWN": 19,
    "LEFT": 5,
    "RIGHT": 26,
    "PRESS": 13,
    "KEY1": 21,
    "KEY2": 20,
    "KEY3": 16,
}
REPEATABLE = {"UP", "DOWN", "LEFT", "RIGHT"}

# Buttons that must never be read on this setup:
#  - joystick DOWN (GPIO 19) and KEY1 (GPIO 21) are the I2S pins of the MAX98357 speaker amp
#    (LRCLK and DATA). Reading them as buttons would also switch the amp's pins to inputs
#    and silence it, so they are left alone.
#  - KEY2 (GPIO 20) is the Pi's I2S DIN pin. The amp doesn't use it, but the hifiberry-dac
#    overlay still claims it, so lgpio cannot read that button.
#  - joystick LEFT is dead on this HAT, but it just never fires, so it's harmless.
# What's left: UP, RIGHT, PRESS, KEY3. RIGHT scrolls down in menus (Screen.right_is_down).
DEAD_BUTTONS = {"DOWN", "KEY1", "KEY2"}


def _find_driver_dir():
    home = os.path.expanduser("~")
    candidates = [
        os.environ.get("DME_LCD_DIR"),
        home + "/1.44inch-LCD-HAT-Code/1.44inch-LCD-HAT-Code/RaspberryPi/python",
        home + "/1.44inch-LCD-HAT-Code/RaspberryPi/python",
    ]
    for path in candidates:
        if path and os.path.isfile(os.path.join(path, "LCD_1in44.py")):
            return path
    raise RuntimeError(
        "Waveshare driver not found. Run setup.sh, or set DME_LCD_DIR to the folder "
        "that contains LCD_1in44.py"
    )


class Display:
    def __init__(self):
        sys.path.insert(0, _find_driver_dir())
        import LCD_1in44  # Waveshare driver

        self._lcd = LCD_1in44.LCD()
        self._lcd.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
        self._lcd.LCD_Clear()

    def show(self, image):
        """Push a 128x128 PIL image to the screen."""
        self._lcd.LCD_ShowImage(image, 0, 0)

    def close(self):
        try:
            from PIL import Image

            self._lcd.LCD_ShowImage(Image.new("RGB", (W, H), (0, 0, 0)), 0, 0)
        except Exception:
            pass


class Input:
    """Polls the buttons ~200x per second and queues presses in `self.events`."""

    DEBOUNCE_READS = 3        # consecutive reads (about 15 ms) before a change counts
    REPEAT_DELAY = 0.40       # seconds held before a direction starts repeating
    REPEAT_RATE = 0.12        # seconds between repeats

    def __init__(self):
        import lgpio

        self._lgpio = lgpio
        self._handle = lgpio.gpiochip_open(0)
        self._pins = {n: p for n, p in PINS.items() if n not in DEAD_BUTTONS}
        try:
            for pin in self._pins.values():
                lgpio.gpio_claim_input(self._handle, pin, lgpio.SET_PULL_UP)
        except lgpio.error as exc:
            raise RuntimeError(
                "Button pins are busy (the Waveshare driver is claiming them). "
                "Run setup.sh once - it patches the driver's config.py."
            ) from exc

        self.events = queue.Queue()
        self.error = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self):
        down_reads = {name: 0 for name in self._pins}
        up_reads = {name: 0 for name in self._pins}
        held = {name: False for name in self._pins}
        next_repeat = {name: 0.0 for name in self._pins}
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                for name, pin in self._pins.items():
                    pressed = self._lgpio.gpio_read(self._handle, pin) == 0
                    if pressed:
                        up_reads[name] = 0
                        down_reads[name] = min(down_reads[name] + 1, 1000)
                        if not held[name] and down_reads[name] >= self.DEBOUNCE_READS:
                            held[name] = True
                            next_repeat[name] = now + self.REPEAT_DELAY
                            self.events.put(name)
                        elif held[name] and name in REPEATABLE and now >= next_repeat[name]:
                            next_repeat[name] = now + self.REPEAT_RATE
                            self.events.put(name)
                    else:
                        down_reads[name] = 0
                        up_reads[name] = min(up_reads[name] + 1, 1000)
                        if up_reads[name] >= self.DEBOUNCE_READS:
                            held[name] = False
                time.sleep(0.005)
        except Exception as exc:  # surfaced to the main loop
            self.error = exc

    def close(self):
        self._stop.set()
        self._thread.join(timeout=1)
        try:
            self._lgpio.gpiochip_close(self._handle)
        except Exception:
            pass
