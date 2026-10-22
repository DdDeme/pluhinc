"""Colour themes. Every screen reads colours through current(), so switching is instant."""

THEMES = {  # insertion order = order shown in the Theme menu
    "Classic Green": {
        "bg": (8, 12, 8), "fg": (140, 255, 160), "accent": (0, 200, 80),
        "dim": (70, 120, 80), "warn": (255, 90, 60),
    },
    "Blue Neon": {
        "bg": (6, 8, 20), "fg": (150, 225, 255), "accent": (0, 160, 255),
        "dim": (70, 95, 135), "warn": (255, 80, 120),
    },
    "Purple": {
        "bg": (14, 8, 22), "fg": (230, 195, 255), "accent": (160, 80, 255),
        "dim": (105, 75, 135), "warn": (255, 90, 90),
    },
    "Amber CRT": {
        "bg": (16, 10, 2), "fg": (255, 205, 100), "accent": (230, 135, 10),
        "dim": (135, 100, 45), "warn": (255, 70, 40),
    },
    "Red Alert": {
        "bg": (20, 4, 4), "fg": (255, 195, 195), "accent": (225, 40, 40),
        "dim": (135, 65, 65), "warn": (255, 230, 60),
    },
}

DEFAULT = "Classic Green"
_current = DEFAULT


def apply(name):
    """Switch theme; unknown names fall back to the default."""
    global _current
    _current = name if name in THEMES else DEFAULT


def current():
    return THEMES[_current]


def current_name():
    return _current
