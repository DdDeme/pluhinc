#!/usr/bin/env python3
"""DME OS v4 entry point:  python3 ~/pluhinc/dme_os.py"""
import logging
import os
import queue
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from dme import settings as settings_mod  # noqa: E402


def main():
    os.makedirs(settings_mod.CONFIG_DIR, exist_ok=True)
    # lgpio drops small notification files in the working directory,
    # so always run from a folder we can write to.
    os.chdir(settings_mod.CONFIG_DIR)
    logging.basicConfig(
        filename=os.path.join(settings_mod.CONFIG_DIR, "dme.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.info("DME OS starting")

    from dme import bluetooth, boot, hal, screens, speaker, theme, ui  # noqa: E402
    from dme.app import App  # noqa: E402
    from dme.inbox import Inbox  # noqa: E402

    settings = settings_mod.Settings()
    logging.info("speaker: %s", speaker.describe())
    theme.apply(settings.get("theme"))
    ui.set_background(settings.get("background"))

    display = hal.Display()
    try:
        boot.play(display, settings.get("background"))
    except Exception:
        logging.exception("boot splash failed")

    inp = hal.Input()
    photo_queue = queue.Queue()
    app = App(display, inp, settings, photo_queue=photo_queue)
    app.push(screens.main_menu())
    bluetooth.start_auto_connect(settings)  # reconnect the saved speaker in the background

    inbox = Inbox(on_photo=photo_queue.put)
    try:
        inbox.start()
    except OSError:
        logging.exception("photo inbox failed to start (port 8000 busy?)")

    try:
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception:
        logging.exception("crash")
        app.show_crash(traceback.format_exc().strip().splitlines()[-1])
        raise
    finally:
        inbox.close()
        app.close()
        logging.info("DME OS stopped")


if __name__ == "__main__":
    main()
