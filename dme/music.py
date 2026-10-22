"""mpv-based music player. Drop audio files into ~/Music and they'll show up here.

Plays to the paired Bluetooth speaker when one is connected (see bluetooth.py),
otherwise to the wired I2S speaker (see speaker.py). Tracks play one after another.
"""
import logging
import os
import signal
import subprocess

from . import bluetooth, theme, ui

log = logging.getLogger("dme")
MUSIC_DIR = os.path.expanduser("~/Music")
EXTS = (".mp3", ".flac", ".wav", ".ogg", ".m4a")


class Player:
    """One mpv subprocess at a time. Pause/resume uses SIGSTOP/SIGCONT so we don't
    need mpv's JSON IPC socket for a simple play/pause/stop transport."""

    def __init__(self):
        self.proc = None
        self.track = None
        self.paused = False
        self._playlist = []
        self._index = 0
        self._audio_args = []

    def play_list(self, paths, index, audio_args=()):
        """Start paths[index]; the rest of the list follows automatically."""
        self._playlist = list(paths)
        self._audio_args = list(audio_args)
        self._start(index)

    def _start(self, index):
        self._kill()
        if not 0 <= index < len(self._playlist):
            return
        self._index = index
        path = self._playlist[index]
        try:
            self.proc = subprocess.Popen(
                ["mpv", "--no-video", "--really-quiet", *self._audio_args, path])
            self.track = os.path.basename(path)
            self.paused = False
        except FileNotFoundError:
            log.exception("mpv not installed - run setup.sh")

    def update(self):
        """Call often: when a track ends by itself, start the next one."""
        if self.proc is not None and self.proc.poll() is not None:
            self.proc = None
            if self._index + 1 < len(self._playlist):
                self._start(self._index + 1)
            else:
                self.stop()

    def toggle_pause(self):
        if not self.proc or self.proc.poll() is not None:
            return
        os.kill(self.proc.pid, signal.SIGCONT if self.paused else signal.SIGSTOP)
        self.paused = not self.paused

    def _kill(self):
        if self.proc and self.proc.poll() is None:
            if self.paused:  # a stopped process can't act on SIGTERM until it's resumed
                os.kill(self.proc.pid, signal.SIGCONT)
            self.proc.terminate()
        self.proc = None

    def stop(self):
        self._kill()
        self._playlist = []
        self.track = None
        self.paused = False

    def playing(self):
        return self.proc is not None and self.proc.poll() is None


_player = Player()  # module-level: survives screen push/pop so music keeps playing


def update():
    _player.update()


def stop_all():
    _player.stop()


class MusicScreen(ui.Screen):
    tick = 0.5

    def __init__(self):
        os.makedirs(MUSIC_DIR, exist_ok=True)
        self.tracks = sorted(f for f in os.listdir(MUSIC_DIR) if f.lower().endswith(EXTS))
        self.index = 0
        self.top = 0
        self.list_rows = ui.VISIBLE - 1  # leave a row for the status footer area

    def on_button(self, app, button):
        count = len(self.tracks)
        if button == "UP" and count:
            self.index = (self.index - 1) % count
        elif button == "DOWN" and count:
            self.index = (self.index + 1) % count
        elif button == "PRESS" and count:
            if _player.playing():
                _player.toggle_pause()
            else:
                paths = [os.path.join(MUSIC_DIR, t) for t in self.tracks]
                _player.play_list(paths, self.index, bluetooth.audio_args(app.settings))
        elif button == "KEY2":
            _player.stop()
        else:
            return False
        if self.index < self.top:
            self.top = self.index
        elif self.index >= self.top + self.list_rows:
            self.top = self.index - self.list_rows + 1
        return True

    def draw(self, d, app):
        t = theme.current()
        y = ui.header(d, "MUSIC")
        if not self.tracks:
            d.text((4, y), "no tracks in ~/Music", font=ui.FONT, fill=t["dim"])
        for i in range(self.top, min(self.top + self.list_rows, len(self.tracks))):
            label = ui.clip(d, self.tracks[i], ui.FONT, ui.W - 20)
            if i == self.index:
                d.rectangle([0, y, ui.W - 1, y + ui.ROW_H - 1], fill=t["accent"])
                d.text((6, y + 1), label, font=ui.FONT, fill=t["bg"])
            else:
                d.text((6, y + 1), label, font=ui.FONT, fill=t["fg"])
            y += ui.ROW_H
        if _player.playing():
            state = "paused" if _player.paused else "playing"
        else:
            state = "stopped"
        ui.footer(d, f"{_player.track or '--'} [{state}] PRESS pause K2 stop")
