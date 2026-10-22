"""A tiny pseudo-3D world with real, collidable walls, walked by a bean.

Floor rendering uses the old SNES "Mode 7" trick: each screen row below the
horizon maps to one depth in the world, so a whole row's worth of floor
colour is computed in one vectorised numpy pass instead of per pixel. Walls
come from the MAP grid below ('#' = wall, '.' = open floor) and are drawn as
shaded vertical strips, sorted back-to-front. Movement is axis-separated
(try X, then Z, independently) so the bean slides along a wall instead of
just stopping dead when it isn't moving straight at it.
"""
import math

import numpy as np
from PIL import Image, ImageDraw

from . import theme, ui

HORIZON = 46
TILE = 48.0           # world units per map cell
CAM_HEIGHT = 34.0
FOV_SCALE = 70.0       # bigger = narrower field of view
MOVE_SPEED = 8.0
TURN_SPEED = 0.12
PLAYER_RADIUS = 9.0
WALL_HALF = TILE / 2.0
WALL_HEIGHT = 56.0

# '#' = wall, '.' = open floor. Edit this to design a different maze/room.
MAP = [
    "########",
    "#......#",
    "#.##.#.#",
    "#.#..#.#",
    "#.#.##.#",
    "#......#",
    "#.####.#",
    "########",
]
ORIGIN_COL = 1  # map cell that sits at world (0, 0) - i.e. the bean's start
ORIGIN_ROW = 1


def _cell(col, row):
    if row < 0 or row >= len(MAP) or col < 0 or col >= len(MAP[0]):
        return "#"
    return MAP[row][col]


def _is_wall_world(x, z):
    col = int(round(x / TILE)) + ORIGIN_COL
    row = int(round(z / TILE)) + ORIGIN_ROW
    return _cell(col, row) == "#"


def _blocked(x, z, r=PLAYER_RADIUS):
    for ox in (-r, r):
        for oz in (-r, r):
            if _is_wall_world(x + ox, z + oz):
                return True
    return False


def _wall_list():
    walls = []
    for row, line in enumerate(MAP):
        for col, ch in enumerate(line):
            if ch == "#":
                wx = (col - ORIGIN_COL) * TILE
                wz = (row - ORIGIN_ROW) * TILE
                walls.append((wx, wz))
    return walls


WALLS = _wall_list()


class World3D(ui.Screen):
    tick = 0.08
    right_is_down = False  # RIGHT turns right here

    def __init__(self):
        self.x = 0.0
        self.z = 0.0
        self.angle = 0.0  # radians, 0 = facing +z

    def on_button(self, app, button):
        if button in ("LEFT", "KEY2"):  # KEY2 turns left (the HAT's LEFT is dead)
            self.angle -= TURN_SPEED
        elif button == "RIGHT":
            self.angle += TURN_SPEED
        elif button == "UP":
            self._move(math.sin(self.angle) * MOVE_SPEED, math.cos(self.angle) * MOVE_SPEED)
        elif button in ("DOWN", "PRESS"):  # PRESS walks back (the HAT's DOWN can't be used)
            self._move(-math.sin(self.angle) * MOVE_SPEED, -math.cos(self.angle) * MOVE_SPEED)
        else:
            return False
        return True

    def _move(self, dx, dz):
        nx = self.x + dx
        if not _blocked(nx, self.z):
            self.x = nx
        nz = self.z + dz
        if not _blocked(self.x, nz):
            self.z = nz

    def full_image(self, app):
        t = theme.current()
        W = H = ui.W
        img = Image.new("RGB", (W, H), (10, 10, 18))
        arr = np.array(img)

        sky_top = np.array((6, 8, 14))
        sky_bot = np.array(t["dim"])
        for y in range(HORIZON):
            f = y / max(HORIZON - 1, 1)
            arr[y, :] = (sky_top * (1 - f) + sky_bot * f).astype(np.uint8)

        cos_a, sin_a = math.cos(self.angle), math.sin(self.angle)
        xs = np.arange(W) - W / 2.0
        for y in range(HORIZON, H):
            depth = CAM_HEIGHT * FOV_SCALE / (y - HORIZON + 1)
            row_x = xs * (depth / FOV_SCALE)
            world_x = self.x + row_x * cos_a + depth * sin_a
            world_z = self.z - row_x * sin_a + depth * cos_a
            tile = (np.floor(world_x / TILE).astype(int) + np.floor(world_z / TILE).astype(int)) & 1
            fog = max(0.0, 1.0 - depth / 900.0)
            base_a = np.array(t["bg"]) * 0.6
            base_b = np.array(t["dim"]) * 0.5
            row_color = np.where(tile[:, None] == 0, base_a, base_b)
            row_color = (row_color * fog).astype(np.uint8)
            arr[y, :, :] = row_color

        img = Image.fromarray(arr, "RGB")
        d = ImageDraw.Draw(img)

        projected = []
        for (wx, wz) in WALLS:
            rel_x = wx - self.x
            rel_z = wz - self.z
            cam_x = rel_x * cos_a - rel_z * sin_a
            cam_z = rel_x * sin_a + rel_z * cos_a
            if cam_z <= 10:
                continue
            scale = FOV_SCALE / cam_z
            sx = W / 2.0 + cam_x * scale
            sw = WALL_HALF * scale
            if sx + sw < 0 or sx - sw > W:
                continue
            top = HORIZON - WALL_HEIGHT * scale
            bottom = HORIZON + CAM_HEIGHT * FOV_SCALE / cam_z
            projected.append((cam_z, sx, sw, top, bottom))
        projected.sort(key=lambda p: -p[0])  # far to near

        for cam_z, sx, sw, top, bottom in projected:
            fog = max(0.2, 1.0 - cam_z / 900.0)
            shade = tuple(int(c * fog) for c in t["fg"])
            d.rectangle([sx - sw, top, sx + sw, bottom], fill=shade, outline=(0, 0, 0))

        # the bean: fixed near screen-bottom-centre (third person), own drop shadow
        bx, by = W / 2.0, H - 16
        d.ellipse([bx - 5, by - 2, bx + 5, by + 3], fill=(0, 0, 0))
        d.ellipse([bx - 6, by - 16, bx + 6, by], fill=t["accent"])
        d.ellipse([bx - 2, by - 13, bx + 1, by - 10], fill=t["bg"])

        ui.footer(d, "UP fwd  PRESS back")
        d.text((4, ui.H - 21), "K2 / RIGHT = turn", font=ui.FONT_SMALL, fill=t["dim"])
        return img

    def draw(self, d, app):
        pass  # unused: full_image() handles everything
