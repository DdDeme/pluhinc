#!/usr/bin/env bash
# One-time setup for DME OS v4 on Raspberry Pi OS Lite (Zero 2 W + Waveshare 1.44" LCD HAT).
# Safe to run more than once.
set -e

echo "== Packages"
sudo apt-get update
sudo apt-get install -y --fix-missing \
    python3-pil python3-numpy python3-spidev python3-gpiozero python3-lgpio \
    fonts-dejavu-core p7zip-full git wget mpv ffmpeg network-manager alsa-utils

echo "== Bluetooth audio (BlueALSA - lets mpv play to a Bluetooth speaker without PulseAudio)"
sudo apt-get install -y --fix-missing bluez bluez-alsa-utils libasound2-plugin-bluez
sudo rfkill unblock bluetooth || true
sudo systemctl enable --now bluetooth || true
sudo systemctl enable --now bluealsa || true
sudo usermod -aG bluetooth "$USER" || true

echo "== Waveshare LCD driver"
NESTED="$HOME/1.44inch-LCD-HAT-Code/1.44inch-LCD-HAT-Code/RaspberryPi/python"
FLAT="$HOME/1.44inch-LCD-HAT-Code/RaspberryPi/python"
if [ ! -f "$NESTED/LCD_1in44.py" ] && [ ! -f "$FLAT/LCD_1in44.py" ]; then
    cd "$HOME"
    wget -q -O lcdhat.7z https://files.waveshare.com/upload/f/fa/1.44inch-LCD-HAT-Code.7z
    7z x -y lcdhat.7z -o1.44inch-LCD-HAT-Code > /dev/null
    rm -f lcdhat.7z
fi
if [ -f "$NESTED/LCD_1in44.py" ]; then DRIVER="$NESTED"; else DRIVER="$FLAT"; fi
echo "driver folder: $DRIVER"

echo "== Patching driver so it stops claiming the button pins"
CFG="$DRIVER/config.py"
if [ ! -f "$CFG.dme-bak" ]; then cp "$CFG" "$CFG.dme-bak"; fi
sed -i -E 's/^([[:space:]]*)(self\.GPIO_KEY[A-Za-z0-9_]*[[:space:]]*=.*)$/\1# dme-disabled: \2/' "$CFG"
echo "patched $CFG (original saved as config.py.dme-bak)"

echo "== SPI"
sudo raspi-config nonint do_spi 0

echo "== I2S speaker (MAX98357A: BCLK=GPIO18, LRCLK=GPIO19, DIN=GPIO21)"
echo "   GPIO19 is the HAT's joystick DOWN and GPIO21 is KEY1, so DME disables both buttons."
CONFIG_TXT="/boot/firmware/config.txt"
if [ ! -f "$CONFIG_TXT" ]; then CONFIG_TXT="/boot/config.txt"; fi
# An earlier version wrote dtoverlay=max98357a,lrclk-pin=16. lrclk-pin is not a
# real max98357a parameter, and GPIO16 is KEY3, so remove that broken line.
sudo sed -i -E '/^[[:space:]]*dtoverlay=max98357a.*lrclk-pin=/d' "$CONFIG_TXT"
if ! grep -q '^dtparam=i2s=on' "$CONFIG_TXT"; then
    echo "dtparam=i2s=on" | sudo tee -a "$CONFIG_TXT" > /dev/null
fi
if grep -qE '^dtoverlay=(max98357a|hifiberry-dac)(,|$)' "$CONFIG_TXT"; then
    echo "I2S overlay already present in $CONFIG_TXT"
else
    echo "dtoverlay=hifiberry-dac" | sudo tee -a "$CONFIG_TXT" > /dev/null
    echo "added dtoverlay=hifiberry-dac to $CONFIG_TXT (reboot required)"
fi

mkdir -p "$HOME/.config/dme_os" "$HOME/dme_files" "$HOME/dme_inbox" "$HOME/Music"

REPO="$(cd "$(dirname "$0")" && pwd)"
if [ "$1" = "--autostart" ]; then
    echo "== Installing the boot-logo and DME OS services"
    for unit in dme-bootlogo dme-os; do
        sed -e "s|__USER__|$USER|g" -e "s|__REPO__|$REPO|g" "$REPO/$unit.service" \
            | sudo tee "/etc/systemd/system/$unit.service" > /dev/null
    done
    sudo systemctl daemon-reload
    sudo systemctl enable dme-bootlogo.service dme-os.service
    echo "DME OS will now start at boot. While developing over SSH, run"
    echo "  sudo systemctl stop dme-os"
    echo "first, or two copies will fight over the screen."
fi
echo
echo "After a reboot, 'aplay -l' should list the I2S card (sndrpihifiberry or MAX98357A)."
echo "DME picks that card by name, so it no longer matters whether it is card 0 or 1."
echo
echo "Photo inbox will listen on port 8000 once DME OS is running - point an"
echo "iPhone Shortcut's 'Get Contents of URL' (POST) at http://<pi-ip>:8000/upload"
echo
echo "Done. Start DME OS with:  python3 $REPO/dme_os.py"
echo "(or run  bash $REPO/setup.sh --autostart  to make it start at boot)"
