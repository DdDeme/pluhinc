"""Bluetooth: pair and connect speakers/headphones, and play audio to them.

Control goes through `bluetoothctl`. Audio goes through BlueALSA (the
bluez-alsa-utils package, installed by setup.sh), so mpv can stream to an A2DP
speaker without needing PulseAudio or PipeWire.

Pairing works for speakers and headphones that pair without a PIN (nearly all
of them). Put the device in pairing mode, press K2 to scan, pick it, press PRESS.
"""
import logging
import re
import subprocess
import threading
import time

from . import speaker, theme, ui

log = logging.getLogger("dme")

_DEVICE = re.compile(r"^Device ([0-9A-Fa-f:]{17}) (.*)$")
_UNNAMED = re.compile(r"^([0-9A-Fa-f]{2}-){5}[0-9A-Fa-f]{2}$")  # bluetoothctl's name for nameless devices
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


# ---------------------------------------------------------------- bluetoothctl ----
def _ctl(*args, timeout=10):
    """Run one bluetoothctl command and return its output ('' if it failed)."""
    try:
        done = subprocess.run(["bluetoothctl", *args], capture_output=True,
                              text=True, timeout=timeout)
        return _ANSI.sub("", done.stdout)
    except subprocess.TimeoutExpired:
        log.warning("bluetoothctl %s timed out", " ".join(args))
    except FileNotFoundError:
        log.warning("bluetoothctl not found - run setup.sh to install bluez")
    except Exception:
        log.exception("bluetoothctl failed (is bluez installed? run setup.sh)")
    return ""


def _parse_devices(out):
    found = {}
    for line in out.splitlines():
        match = _DEVICE.match(line.strip())
        if match:
            found[match.group(1).upper()] = match.group(2).strip()
    return found


def list_devices():
    """[(mac, name, paired, connected)] - connected first, then paired, then the rest."""
    everything = _parse_devices(_ctl("devices"))
    paired = _parse_devices(_ctl("devices", "Paired"))
    connected = _parse_devices(_ctl("devices", "Connected"))
    everything.update(paired)
    rows = []
    for mac, name in everything.items():
        if mac not in paired and _UNNAMED.match(name):
            continue  # hide the nameless random devices that are always nearby
        rows.append((mac, name, mac in paired, mac in connected))
    rows.sort(key=lambda r: (not r[3], not r[2], r[1].lower()))
    return rows


def is_powered():
    return "Powered: yes" in _ctl("show")


def set_power(on):
    if on:
        try:  # a fresh install can leave Bluetooth soft-blocked
            subprocess.run(["sudo", "rfkill", "unblock", "bluetooth"],
                           capture_output=True, timeout=5)
        except Exception:
            pass
    _ctl("power", "on" if on else "off")


def is_connected(mac):
    return "Connected: yes" in _ctl("info", mac)


def _is_paired(mac):
    return "Paired: yes" in _ctl("info", mac)


def scan(seconds=8):
    _ctl("--timeout", str(seconds), "scan", "on", timeout=seconds + 5)


def _pair(mac):
    out = _ctl("pair", mac, timeout=30).lower()
    if "successful" in out or "already exists" in out or _is_paired(mac):
        return True
    # some devices need an agent that accepts the pairing automatically
    out = _ctl("--agent", "NoInputNoOutput", "pair", mac, timeout=30).lower()
    return "successful" in out or _is_paired(mac)


def connect_device(mac, name, settings):
    """Pair (if needed), trust and connect. Returns a short status message."""
    if not _is_paired(mac) and not _pair(mac):
        return "pairing failed - pairing mode?"
    _ctl("trust", mac)
    _ctl("connect", mac, timeout=20)
    if is_connected(mac):
        settings.set("bt_device", mac)
        settings.save()
        return f"connected: {name}"
    return "connect failed - is it on?"


def disconnect_device(mac, name):
    _ctl("disconnect", mac)
    return f"disconnected: {name}"


def remove_device(mac, name, settings):
    _ctl("remove", mac)
    if settings.get("bt_device") == mac:
        settings.set("bt_device", "")
        settings.save()
    return f"forgot: {name}"


# ----------------------------------------------------------------------- audio ----
def audio_args(settings):
    """Extra mpv arguments for the right output:
    - the saved Bluetooth device, while it's connected
    - otherwise the wired I2S speaker (see dme/speaker.py), unless it's turned off
    - otherwise mute, so flipping the speaker off is actually silent"""
    mac = settings.get("bt_device")
    if mac and is_connected(mac):
        return ["--ao=alsa", f"--audio-device=alsa/bluealsa:DEV={mac},PROFILE=a2dp"]
    if settings.get("local_speaker"):
        return speaker.audio_args()
    return ["--ao=null"]


def start_auto_connect(settings):
    """At startup, try to reconnect the saved speaker in the background."""
    mac = settings.get("bt_device")
    if not mac:
        return

    def run():
        for _ in range(4):
            try:
                if is_connected(mac):
                    return
                set_power(True)
                _ctl("connect", mac, timeout=15)
                if is_connected(mac):
                    log.info("bluetooth: reconnected %s", mac)
                    return
            except Exception:
                log.exception("bluetooth auto-connect failed")
            time.sleep(6)
        log.info("bluetooth: %s not reachable at startup", mac)

    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------------- screen ----
class BluetoothScreen(ui.Screen):
    """Row 0 switches Bluetooth on/off; the rest are devices.
    PRESS connect/disconnect   K2 scan   K3 back"""

    tick = 0.5

    def __init__(self):
        self.devices = []
        self.powered = True
        self.index = 0
        self.top = 0
        self.busy = False
        self.status = ""

    def on_enter(self, app):
        self._task(app, "loading...", lambda: "")  # _task reloads the list when it finishes

    # ---- background work (bluetoothctl can take seconds; never block the UI) ----
    def _task(self, app, label, fn):
        if self.busy:
            return
        self.busy = True
        self.status = label

        def run():
            try:
                self.status = fn() or ""
            except Exception:
                log.exception("bluetooth task failed")
                self.status = "error - see dme.log"
            finally:
                self._load()
                self.busy = False
                app.dirty = True

        threading.Thread(target=run, daemon=True).start()

    def _load(self):
        # keep the cursor on the same device when the list re-sorts (connected ones float to the top)
        selected = None
        if 0 < self.index <= len(self.devices):
            selected = self.devices[self.index - 1][0]
        self.powered = is_powered()
        devices = list_devices()
        if selected:
            for i, row in enumerate(devices):
                if row[0] == selected:
                    self.index = i + 1
                    break
        self.devices = devices
        self.index = min(self.index, len(self.devices))
        if self.index < self.top:
            self.top = self.index
        elif self.index >= self.top + ui.VISIBLE:
            self.top = self.index - ui.VISIBLE + 1
        return ""

    def _toggle_power(self):
        set_power(not self.powered)
        return ""

    def _scan(self):
        if not is_powered():
            set_power(True)
        scan(8)
        return "scan done"

    # ---- input ------------------------------------------------------------------
    def on_button(self, app, button):
        rows = len(self.devices) + 1
        if button == "UP":
            self.index = (self.index - 1) % rows
        elif button == "DOWN":
            self.index = (self.index + 1) % rows
        elif button in ("PRESS", "RIGHT"):
            self._activate(app)
        elif button == "KEY2":
            self._task(app, "scanning...", self._scan)
        else:
            return False
        if self.index < self.top:
            self.top = self.index
        elif self.index >= self.top + ui.VISIBLE:
            self.top = self.index - ui.VISIBLE + 1
        return True

    def _activate(self, app):
        if self.index == 0:
            self._task(app, "switching...", self._toggle_power)
            return
        mac, name, _paired, connected = self.devices[self.index - 1]
        if connected:
            self._task(app, "disconnecting...", lambda: disconnect_device(mac, name))
        else:
            self._task(app, f"connecting {name}...",
                       lambda: connect_device(mac, name, app.settings))

    # ---- drawing ------------------------------------------------------------------
    def draw(self, d, app):
        t = theme.current()
        y = ui.header(d, "BLUETOOTH", right="busy" if self.busy else None)
        rows = [(f"Bluetooth: {'ON' if self.powered else 'OFF'}", False)]
        for _mac, name, paired, connected in self.devices:
            prefix = "* " if connected else ("+ " if paired else "  ")
            rows.append((prefix + name, connected))
        for i in range(self.top, min(self.top + ui.VISIBLE, len(rows))):
            label, connected = rows[i]
            label = ui.clip(d, label, ui.FONT, ui.W - 12)
            if i == self.index:
                d.rectangle([0, y, ui.W - 1, y + ui.ROW_H - 1], fill=t["accent"])
                d.text((6, y + 1), label, font=ui.FONT, fill=t["bg"])
            else:
                d.text((6, y + 1), label, font=ui.FONT,
                       fill=t["accent"] if connected else t["fg"])
            y += ui.ROW_H
        ui.footer(d, self.status or "K2 scan  PRESS connect")
