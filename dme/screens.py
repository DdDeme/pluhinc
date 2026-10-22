"""The screens that make up the v4 core: menus, system monitor, theme picker, power."""
from . import __version__, speaker, sysinfo, theme, ui
from .bluetooth import BluetoothScreen
from .files import FilesScreen
from .games import games_menu
from .music import MusicScreen
from .tools import tools_menu
from .wifi import WifiScreen


# ---------------------------------------------------------------- System ----
class SystemScreen(ui.Screen):
    tick = 1.0

    def __init__(self):
        self.cpu = sysinfo.CpuMeter()

    @staticmethod
    def _meter(d, y, label, value, fraction):
        t = theme.current()
        d.text((4, y), label, font=ui.FONT, fill=t["dim"])
        w = d.textlength(value, font=ui.FONT)
        d.text((ui.W - 4 - w, y), value, font=ui.FONT, fill=t["fg"])
        ui.bar(d, 4, y + 12, ui.W - 8, 4, fraction)

    def draw(self, d, app):
        y = ui.header(d, "SYSTEM")
        cpu = self.cpu.percent()
        ram_used, ram_total, ram_frac = sysinfo.memory()
        disk_used, disk_total, disk_frac = sysinfo.disk()
        self._meter(d, y, "CPU", f"{cpu:.0f}%", cpu / 100.0)
        y += 18
        self._meter(d, y, "RAM", f"{ram_used:.0f}/{ram_total:.0f}M", ram_frac)
        y += 18
        self._meter(d, y, "DISK", f"{disk_used:.1f}/{disk_total:.0f}G", disk_frac)
        y += 18
        temp = sysinfo.cpu_temp()
        ui.kv(d, y, "TEMP", "n/a" if temp is None else f"{temp:.1f}C",
              warn=temp is not None and temp >= 70)
        y += 13
        ui.kv(d, y, "IP", sysinfo.ip_address())
        y += 13
        ui.kv(d, y, "UP", sysinfo.uptime())


# ----------------------------------------------------------------- Theme ----
class ThemeScreen(ui.Screen):
    """Highlighting a theme previews it live. PRESS keeps it, KEY3 reverts."""

    def __init__(self):
        self.names = list(theme.THEMES)
        self.original = theme.current_name()
        self.index = self.names.index(self.original)

    def on_enter(self, app):
        self.original = theme.current_name()
        self.index = self.names.index(self.original)

    def on_button(self, app, button):
        if button in ("UP", "DOWN"):
            step = -1 if button == "UP" else 1
            self.index = (self.index + step) % len(self.names)
            theme.apply(self.names[self.index])
            return True
        if button in ("PRESS", "RIGHT"):
            app.settings.set("theme", self.names[self.index])
            app.settings.save()
            app.pop()
            return True
        if button == "KEY3":
            theme.apply(self.original)
            app.pop()
            return True
        return False

    def draw(self, d, app):
        t = theme.current()
        y = ui.header(d, "THEME")
        for i, name in enumerate(self.names):
            if i == self.index:
                d.rectangle([0, y, ui.W - 1, y + ui.ROW_H - 1], fill=t["accent"])
                d.text((6, y + 1), name, font=ui.FONT, fill=t["bg"])
            else:
                d.text((6, y + 1), name, font=ui.FONT, fill=t["fg"])
            y += ui.ROW_H
        # palette preview strip
        x = 6
        for key in ("accent", "fg", "dim", "warn"):
            d.rectangle([x, 100, x + 24, 108], fill=t[key])
            x += 29
        ui.footer(d, "PRESS keep  K3 undo")


# ----------------------------------------------------------------- About ----
class AboutScreen(ui.Screen):
    def draw(self, d, app):
        t = theme.current()
        y = ui.header(d, "ABOUT")
        d.text((4, y), "DME OS", font=ui.FONT_BOLD, fill=t["accent"])
        y += 15
        d.text((4, y), f"v{__version__}", font=ui.FONT, fill=t["fg"])
        y += 14
        d.text((4, y), sysinfo.hostname(), font=ui.FONT, fill=t["dim"])
        y += 20
        for line in ("UP     up", "RIGHT  down", "PRESS  select", "KEY3   back"):
            d.text((4, y), line, font=ui.FONT, fill=t["fg"])
            y += 12


# ----------------------------------------------------------------- Power ----
class ConfirmScreen(ui.Screen):
    def __init__(self, title, question, on_yes):
        self.title = title
        self.question = question
        self.on_yes = on_yes
        self.index = 0  # 0 = No (safe default), 1 = Yes

    def on_button(self, app, button):
        if button in ("UP", "DOWN"):
            self.index ^= 1
            return True
        if button in ("PRESS", "RIGHT"):
            app.pop()
            if self.index == 1:
                self.on_yes(app)
            return True
        return False

    def draw(self, d, app):
        t = theme.current()
        y = ui.header(d, self.title)
        d.text((6, y + 8), self.question, font=ui.FONT, fill=t["fg"])
        y += 36
        for i, label in enumerate(("No", "Yes")):
            if i == self.index:
                d.rectangle([0, y, ui.W - 1, y + ui.ROW_H - 1], fill=t["accent"])
                d.text((6, y + 1), label, font=ui.FONT, fill=t["bg"])
            else:
                d.text((6, y + 1), label, font=ui.FONT, fill=t["fg"])
            y += ui.ROW_H


def power_menu():
    def ask(title, question, action):
        return lambda app: app.push(ConfirmScreen(title, question, action))

    return ui.MenuScreen("POWER", [
        ("Shutdown", ask("SHUTDOWN", "Shut down?", lambda app: app.power("poweroff"))),
        ("Reboot", ask("REBOOT", "Reboot now?", lambda app: app.power("reboot"))),
        ("Exit DME", lambda app: app.quit()),
    ])


# ------------------------------------------------------------- Menus --------
def settings_menu(app):
    def bg_label(on):
        return f"Background: {'on' if on else 'off'}"

    def toggle_background(app):
        on = not app.settings.get("background")
        app.settings.set("background", on)
        app.settings.save()
        ui.set_background(on)
        menu.items[2] = (bg_label(on), toggle_background)

    def speaker_label(on):
        if not on:
            return "Speaker: off"
        return "Speaker: on (I2S)" if speaker.find_card() else "Speaker: on"

    def toggle_speaker(app):
        on = not app.settings.get("local_speaker")
        app.settings.set("local_speaker", on)
        app.settings.save()
        menu.items[3] = (speaker_label(on), toggle_speaker)

    menu = ui.MenuScreen("SETTINGS", [
        ("Theme", lambda app: app.push(ThemeScreen())),
        ("Bluetooth", lambda app: app.push(BluetoothScreen())),
        (bg_label(app.settings.get("background")), toggle_background),
        (speaker_label(app.settings.get("local_speaker")), toggle_speaker),
        ("WiFi", lambda app: app.push(WifiScreen())),
        ("About", lambda app: app.push(AboutScreen())),
    ])
    return menu


def main_menu():
    return ui.MenuScreen("DME OS", [
        ("System", lambda app: app.push(SystemScreen())),
        ("Files", lambda app: app.push(FilesScreen())),
        ("Music", lambda app: app.push(MusicScreen())),
        ("Games", lambda app: app.push(games_menu())),
        ("Tools", lambda app: app.push(tools_menu())),
        ("Settings", lambda app: app.push(settings_menu(app))),
        ("Power", lambda app: app.push(power_menu())),
    ], footer_text="UP=up R=dn  PRESS ok")
