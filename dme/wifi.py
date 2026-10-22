"""Read-only WiFi status + scan.

Entering a password needs a real keyboard, which this device doesn't have, so
this screen deliberately doesn't try to connect to anything - it just shows
what's currently associated and what's nearby. To connect to a new network,
SSH in and run:
    sudo nmcli device wifi connect "SSID" password "PASSWORD"
"""
import logging
import subprocess

from . import theme, ui

log = logging.getLogger("dme")


def _run(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=6).stdout
    except Exception:
        log.exception("nmcli call failed (is network-manager installed?)")
        return ""


def _current():
    out = _run(["nmcli", "-t", "-f", "active,ssid,signal", "device", "wifi"])
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[0] == "yes":
            return parts[1]
    return None


def _scan():
    out = _run(["nmcli", "-t", "-f", "ssid,signal", "device", "wifi", "list"])
    seen, nets = set(), []
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) < 2 or not parts[0] or parts[0] in seen:
            continue
        seen.add(parts[0])
        nets.append((parts[0], parts[1]))
    return sorted(nets, key=lambda n: -int(n[1] or 0))


class WifiScreen(ui.Screen):
    tick = None

    def __init__(self):
        self.current = _current()
        self.networks = _scan()
        self.index = 0
        self.top = 0
        self.list_rows = ui.VISIBLE - 2

    def on_button(self, app, button):
        count = len(self.networks)
        if button == "UP" and count:
            self.index = (self.index - 1) % count
        elif button == "DOWN" and count:
            self.index = (self.index + 1) % count
        elif button == "KEY2":
            self.current = _current()
            self.networks = _scan()
        else:
            return False
        if self.index < self.top:
            self.top = self.index
        elif self.index >= self.top + self.list_rows:
            self.top = self.index - self.list_rows + 1
        return True

    def draw(self, d, app):
        t = theme.current()
        y = ui.header(d, "WIFI")
        d.text((4, y), f"on: {self.current or 'not connected'}", font=ui.FONT, fill=t["fg"])
        y += 14
        for i in range(self.top, min(self.top + self.list_rows, len(self.networks))):
            ssid, signal = self.networks[i]
            label = ui.clip(d, ssid, ui.FONT, ui.W - 30)
            if i == self.index:
                d.rectangle([0, y, ui.W - 1, y + ui.ROW_H - 1], fill=t["accent"])
                d.text((6, y + 1), label, font=ui.FONT, fill=t["bg"])
                d.text((ui.W - 24, y + 1), f"{signal}", font=ui.FONT_SMALL, fill=t["bg"])
            else:
                d.text((6, y + 1), label, font=ui.FONT, fill=t["fg"])
                d.text((ui.W - 24, y + 1), f"{signal}", font=ui.FONT_SMALL, fill=t["dim"])
            y += ui.ROW_H
        ui.footer(d, "K2 rescan  connect via ssh")
