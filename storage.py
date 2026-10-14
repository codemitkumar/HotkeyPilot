"""Saving shortcuts and the start-with-Windows setting."""

import json
import logging
import os
import sys
import uuid
import winreg

log = logging.getLogger(__name__)

APP_NAME = "HotkeyPilot"
DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_PATH = os.path.join(DATA_DIR, "shortcuts.json")
LOG_PATH = os.path.join(DATA_DIR, "hotkeypilot.log")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def new_id():
    return uuid.uuid4().hex[:12]


def _default_shortcuts():
    """First-run examples: Ctrl+Shift+E opens Edge, holding W for 3s opens WhatsApp."""
    from actions import list_start_apps
    try:
        apps = {a["Name"].lower(): a for a in list_start_apps()}
    except Exception:
        log.exception("Could not list installed apps")
        apps = {}
    defaults = [{
        "id": new_id(), "name": "Microsoft Edge", "enabled": True,
        "trigger": {"type": "combo", "modifiers": ["ctrl", "shift"], "key": "E"},
        "action": {"type": "app", "target": apps.get("microsoft edge", {}).get("AppID", "MSEdge"),
                   "label": "Microsoft Edge"},
    }]
    wa = next((a for name, a in apps.items() if "whatsapp" in name), None)
    if wa:
        defaults.append({
            "id": new_id(), "name": "WhatsApp", "enabled": True,
            "trigger": {"type": "hold", "key": "W", "seconds": 3},
            "action": {"type": "app", "target": wa["AppID"], "label": wa["Name"]},
        })
    return defaults


def load_shortcuts():
    if not os.path.exists(CONFIG_PATH):
        shortcuts = _default_shortcuts()
        save_shortcuts(shortcuts)
        return shortcuts
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f).get("shortcuts", [])
    except Exception:
        log.exception("Could not read %s", CONFIG_PATH)
        backup = CONFIG_PATH + ".broken"
        os.replace(CONFIG_PATH, backup)
        return []


def save_shortcuts(shortcuts):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "shortcuts": shortcuts}, f, indent=2)
    os.replace(tmp, CONFIG_PATH)


def _launch_command():
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        pyw = exe[:-len("python.exe")] + "pythonw.exe"
        if os.path.exists(pyw):
            exe = pyw
    if getattr(sys, "frozen", False):
        return f'"{exe}" --minimized'
    main = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return f'"{exe}" "{main}" --minimized'


def get_autostart():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass
