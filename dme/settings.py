"""Persistent settings, stored as JSON in ~/.config/dme_os/config.json."""
import json
import os

CONFIG_DIR = os.path.expanduser("~/.config/dme_os")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "theme": "Classic Green",
    "volume": 70,
    "background": True,   # faded photo behind the screens
    "bt_device": "",      # MAC of the Bluetooth speaker/headphones to play audio to
    "local_speaker": True, # play on the wired I2S speaker (detected by name) when no Bluetooth device is connected
}


class Settings:
    def __init__(self):
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                self.data.update(stored)
        except (OSError, ValueError):
            pass  # first run or a damaged file: keep the defaults

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, CONFIG_PATH)  # atomic: a power cut can't leave half a file

    def get(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        self.data[key] = value
