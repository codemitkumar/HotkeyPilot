"""HotkeyPilot - custom global keyboard shortcuts that run in the system tray."""

import ctypes
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pystray  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import storage  # noqa: E402
from actions import run_action  # noqa: E402
from engine import HotkeyEngine  # noqa: E402
from ui import App  # noqa: E402
from version import __version__  # noqa: E402

log = logging.getLogger("hotkeypilot")


def make_icon(size=64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.rounded_rectangle((2 * s, 2 * s, 62 * s, 62 * s), radius=14 * s, fill=(37, 99, 235))
    d.rounded_rectangle((8 * s, 8 * s, 56 * s, 52 * s), radius=9 * s, fill=(59, 130, 246))
    bolt = [(36, 10), (18, 36), (30, 36), (26, 54), (46, 26), (34, 26), (38, 10)]
    d.polygon([(x * s, y * s) for x, y in bolt], fill=(255, 255, 255))
    return img


def single_instance():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.CreateMutexW(None, False, "Local\\HotkeyPilotSingleInstance")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.user32.MessageBoxW(None, "HotkeyPilot is already running.\nLook for its icon in the "
                                         "system tray (near the clock).", "HotkeyPilot", 0x40)
        sys.exit(0)
    return handle


def main():
    os.makedirs(storage.DATA_DIR, exist_ok=True)
    # force=True: an early warning from any library would otherwise make basicConfig a no-op.
    logging.basicConfig(filename=storage.LOG_PATH, level=logging.INFO, force=True, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log.info("HotkeyPilot %s starting (%s)", __version__, " ".join(sys.argv))
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    _mutex = single_instance()  # noqa: F841 - keep the handle alive

    icon_img = make_icon()
    app = None

    def on_trigger(sc):
        log.info("Triggered %s", sc.get("name"))
        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY: let the launched app take focus
        try:
            run_action(sc["action"])
        except Exception as e:
            log.exception("Action failed for %s", sc.get("name"))
            if app and app.tray:
                app.tray.notify(f"{sc.get('name')}: {e}", "Shortcut failed")

    shortcuts = storage.load_shortcuts()
    engine = HotkeyEngine(on_trigger)
    engine.set_shortcuts(shortcuts)
    engine.start()

    app = App(engine, shortcuts, start_hidden="--minimized" in sys.argv, icon_image=icon_img)

    menu = pystray.Menu(
        pystray.MenuItem("Open HotkeyPilot", lambda: app.post(app.show), default=True),
        pystray.MenuItem("Pause shortcuts", lambda: app.post(app.set_paused, not engine.paused),
                         checked=lambda item: engine.paused),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", lambda: app.post(app.quit)),
    )
    app.tray = pystray.Icon("HotkeyPilot", icon_img, "HotkeyPilot", menu)
    app.tray.run_detached()
    if "--minimized" in sys.argv:  # started with Windows: say we're alive, since no window opens
        app.root.after(1500, lambda: app.tray.notify("Your shortcuts are active. Open me from the tray icon.",
                                                      "HotkeyPilot is running"))

    try:
        app.run()
    finally:
        engine.stop()
        app.tray.stop()


if __name__ == "__main__":
    main()
