"""A small Snake game, playable with the joystick."""
import random

from . import theme, ui
from .world3d import World3D

GRID = 16  # 16x16 cells on the 128x128 screen -> 8px cells
CELL = ui.W // GRID


class SnakeGame(ui.Screen):
    tick = 0.15
    use_background = False  # keep the playfield clean
    right_is_down = False   # RIGHT turns right here

    def __init__(self):
        self._reset()

    def _reset(self):
        mid = GRID // 2
        self.snake = [(mid, mid), (mid - 1, mid), (mid - 2, mid)]
        self.direction = (1, 0)
        self.next_direction = (1, 0)
        self.food = self._place_food()
        self.alive = True
        self.score = 0

    def _place_food(self):
        while True:
            pos = (random.randrange(GRID), random.randrange(GRID))
            if pos not in self.snake:
                return pos

    def on_button(self, app, button):
        # Two-button steering (the HAT's DOWN, LEFT and KEY1 can't be used):
        # RIGHT turns clockwise, KEY2 turns counter-clockwise, relative to the way you're heading.
        if button in ("RIGHT", "KEY2"):
            dx, dy = self.direction  # last heading actually moved, so quick double presses can't U-turn
            self.next_direction = (-dy, dx) if button == "RIGHT" else (dy, -dx)
            return True
        if button == "PRESS" and not self.alive:
            self._reset()
            return True
        return False

    def _step(self):
        self.direction = self.next_direction
        hx, hy = self.snake[0]
        dx, dy = self.direction
        new_head = ((hx + dx) % GRID, (hy + dy) % GRID)
        if new_head in self.snake:
            self.alive = False
            return
        self.snake.insert(0, new_head)
        if new_head == self.food:
            self.score += 1
            self.food = self._place_food()
        else:
            self.snake.pop()

    def draw(self, d, app):
        if self.alive:
            self._step()
        t = theme.current()
        for (x, y) in self.snake:
            d.rectangle([x * CELL, y * CELL, x * CELL + CELL - 2, y * CELL + CELL - 2],
                        fill=t["accent"])
        fx, fy = self.food
        d.rectangle([fx * CELL, fy * CELL, fx * CELL + CELL - 2, fy * CELL + CELL - 2],
                    fill=t["warn"])
        d.text((2, 0), f"{self.score}", font=ui.FONT_SMALL, fill=t["dim"])
        if not self.alive:
            msg = "GAME OVER  PRESS"
            w = d.textlength(msg, font=ui.FONT_SMALL)
            d.text(((ui.W - w) / 2, ui.H // 2 - 4), msg, font=ui.FONT_SMALL, fill=t["warn"])


def games_menu():
    """Later games just add another row here."""
    return ui.MenuScreen("GAMES", [
        ("Snake", lambda app: app.push(SnakeGame())),
        ("3D Walk", lambda app: app.push(World3D())),
    ])
