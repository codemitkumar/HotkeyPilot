"""What a shortcut can do when it fires."""

import json
import os
import re
import subprocess
import winreg

CREATE_NO_WINDOW = 0x08000000

ACTION_TYPES = [
    ("app", "Open an installed app"),
    ("url", "Open websites"),
    ("program", "Open a program or file"),
    ("folder", "Open a folder"),
    ("command", "Run a command"),
]
ACTION_LABELS = dict(ACTION_TYPES)

# id -> (label, exe name in App Paths, fallback paths, private flag, new-window flag)
BROWSERS = {
    "default": ("Default browser", None, [], None, None),
    "edge": ("Microsoft Edge", "msedge.exe",
             [r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
              r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"], "--inprivate", "--new-window"),
    "chrome": ("Google Chrome", "chrome.exe",
               [r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
                r"%LocalAppData%\Google\Chrome\Application\chrome.exe"], "--incognito", "--new-window"),
    "firefox": ("Firefox", "firefox.exe",
                [r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
                 r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"], "-private-window", "-new-window"),
    "brave": ("Brave", "brave.exe",
              [r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
               r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe"], "--incognito", "--new-window"),
}


def split_urls(text):
    """Accept URLs separated by spaces, commas or new lines; add https:// when missing."""
    urls = []
    for part in re.split(r"[\s,]+", text.strip()):
        if not part:
            continue
        if "://" not in part and not part.startswith(("mailto:", "whatsapp:")):
            part = "https://" + part
        urls.append(part)
    return urls


def find_browser(browser_id):
    _, exe, fallbacks, _, _ = BROWSERS[browser_id]
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as k:
                path = os.path.expandvars(winreg.QueryValueEx(k, "")[0].strip('"'))
                if os.path.exists(path):
                    return path
        except OSError:
            pass
    for path in fallbacks:
        path = os.path.expandvars(path)
        if os.path.exists(path):
            return path
    return None


def installed_browsers():
    return [bid for bid in BROWSERS if bid == "default" or find_browser(bid)]


def open_urls(urls, browser_id="default", private=False, new_window=False):
    if not urls:
        raise ValueError("No website address given")
    if browser_id == "default" or browser_id not in BROWSERS:
        if private:
            raise ValueError("Pick a specific browser to open a private window")
        for url in urls:
            os.startfile(url)
        return
    label, _, _, private_flag, window_flag = BROWSERS[browser_id]
    exe = find_browser(browser_id)
    if not exe:
        raise FileNotFoundError(f"{label} isn't installed")
    args = [exe]
    if private:
        args.append(private_flag)
    elif new_window:
        args.append(window_flag)
    subprocess.Popen(args + urls)


def run_action(action):
    kind = action.get("type")
    target = os.path.expandvars(action.get("target", "").strip())
    args = action.get("args", "").strip()
    if not target:
        raise ValueError("Shortcut has no target")

    if kind == "app":
        # Works for Store apps (WhatsApp) and classic apps listed in the Start menu.
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{target}"])
    elif kind == "program":
        cwd = os.path.dirname(target) or None
        os.startfile(target, "open", args, cwd if cwd and os.path.isdir(cwd) else None)
    elif kind == "folder":
        os.startfile(target)
    elif kind == "url":
        open_urls(split_urls(target), action.get("browser", "default"),
                  action.get("private", False), action.get("new_window", False))
    elif kind == "command":
        subprocess.Popen(target, shell=True, creationflags=CREATE_NO_WINDOW)
    else:
        raise ValueError(f"Unknown action type: {kind}")


def describe_action(action):
    kind = action.get("type")
    if kind == "url":
        urls = split_urls(action.get("target", ""))
        where = BROWSERS.get(action.get("browser", "default"), BROWSERS["default"])[0]
        first = re.sub(r"^https?://(www\.)?", "", urls[0]).rstrip("/") if urls else ""
        sites = first if len(urls) == 1 else f"{len(urls)} sites"
        extra = " (private)" if action.get("private") else ""
        return f"Open {sites} in {where}{extra}"
    target = action.get("label") or action.get("target", "")
    verb = {"app": "Open", "program": "Open", "folder": "Open folder", "command": "Run"}.get(kind, "")
    return f"{verb} {target}".strip()


def list_start_apps():
    """Installed apps from the Start menu, as [{'Name':..., 'AppID':...}]."""
    script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
              "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress")
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, timeout=60, creationflags=CREATE_NO_WINDOW)
    data = json.loads(out.stdout.decode("utf-8-sig") or "[]")
    if isinstance(data, dict):
        data = [data]
    apps = [a for a in data if a.get("Name") and a.get("AppID")]
    return sorted(apps, key=lambda a: a["Name"].lower())
