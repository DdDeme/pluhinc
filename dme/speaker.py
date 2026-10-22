"""Find the wired I2S speaker (MAX98357A) and give mpv the right ALSA device.

The MAX98357A has no control interface, so Linux sees it as a plain sound card.
Depending on which overlay is loaded it is called something like
"sndrpihifiberry" (hifiberry-dac) or "MAX98357A" (max98357a). Card numbers move
around when HDMI, USB or Bluetooth devices are present, so never assume card 0:
match the card by name instead.
"""
import logging
import re

log = logging.getLogger("dme")

_CARD = re.compile(r"^\s*(\d+)\s+\[([^\]]*)\]:\s+(\S+)\s+-\s+(.*)$")

# A card with one of these words in its name is never the I2S amp.
_NOT_I2S = ("hdmi", "headphone", "bcm2835", "vc4", "usb", "webcam", "camera", "codec")
_I2S_HINTS = ("hifiberry", "max98357", "i2s", "dac", "speaker", "amp")


def parse_cards(text):
    """Parse /proc/asound/cards into [{index, id, driver, name, description}]."""
    cards = []
    current = None
    for line in text.splitlines():
        match = _CARD.match(line)
        if match:
            current = {
                "index": int(match.group(1)),
                "id": match.group(2).strip(),
                "driver": match.group(3).strip(),
                "name": match.group(4).strip(),
                "description": "",
            }
            cards.append(current)
        elif current is not None:
            description = line.strip()
            if description and not description.startswith("---"):
                current["description"] = description
                current = None
    return cards


def _cards():
    try:
        with open("/proc/asound/cards", "r", encoding="utf-8") as f:
            return parse_cards(f.read())
    except OSError:
        return []


def _card_text(card):
    return " ".join(str(card.get(key, "")) for key in
                    ("id", "driver", "name", "description")).lower()


def _excluded(card):
    return any(word in _card_text(card) for word in _NOT_I2S)


def _looks_like_i2s(card):
    if _excluded(card):
        return False
    return any(word in _card_text(card) for word in _I2S_HINTS)


def find_card():
    """Return the I2S card dict, or None when the overlay isn't loaded."""
    cards = _cards()
    for card in cards:
        if _looks_like_i2s(card):
            return card
    # If the overlay gives the card an unexpected name, use the only card that
    # isn't HDMI/onboard/USB. With HDMI + headphones + one I2S amp that is safe.
    remaining = [card for card in cards if not _excluded(card)]
    if len(remaining) == 1:
        log.info("speaker: using the only non-HDMI/USB card: %s", remaining[0]["id"])
        return remaining[0]
    return None


def audio_args():
    """mpv arguments that force ALSA and target the I2S card when it exists.

    mpv's default audio output tries PipeWire/JACK first on some installs, which
    is why a missing server showed up as "couldn't open play stream" even
    though the speaker itself was fine. ALSA is the only stack DME uses.
    """
    card = find_card()
    if card is None:
        log.warning("speaker: no I2S card found - using the ALSA default")
        return ["--ao=alsa"]
    device = f"plughw:CARD={card['id']},DEV=0"
    log.info("speaker: using I2S card %s (%s)", card["id"], card["name"])
    return ["--ao=alsa", f"--audio-device=alsa/{device}"]


def describe():
    """Short human-readable status for the log, e.g. 'sndrpihifiberry (Hifiberry DAC)'."""
    card = find_card()
    if card is None:
        return "no I2S card"
    return f"{card['id']} ({card['name']})"
