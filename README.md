# HotkeyPilot

A small Windows tray app for your own global keyboard shortcuts.

- **Key combinations**, e.g. `Ctrl+Shift+E` opens Microsoft Edge
- **Press-and-hold**, e.g. hold `W` for 3 seconds to open WhatsApp. A quick tap still types `w` as normal.
- Actions: open an installed app (Store apps like WhatsApp work too), open websites, a program or file, a folder, or run a command
- Website shortcuts can open several sites at once in the browser you pick (default, Edge, Chrome, Firefox, Brave), optionally in a private or new window
- Record shortcuts by pressing them, turn them on/off, pause everything from the tray, and start with Windows

## Run

```bash
pip install -r requirements.txt
```

Then double-click `start.bat`, or run `pythonw main.py` to start without a console window.
Closing the window keeps it running in the system tray. Right-click the tray icon to pause or quit.

## Build the exe and installer

Needs [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`).

```bash
powershell -ExecutionPolicy Bypass -File build.ps1
```

- `dist\HotkeyPilot\HotkeyPilot.exe`: the app folder, runnable as-is
- `dist\HotkeyPilot-Setup-<version>.exe`: the installer (the version comes from `version.py`). It installs per user with no admin prompt, offers desktop and
  start-with-Windows options, and adds an uninstaller.

## Where things are stored

- Shortcuts: `%APPDATA%\HotkeyPilot\shortcuts.json`
- Log: `%APPDATA%\HotkeyPilot\hotkeypilot.log`
- "Start with Windows" adds a `HotkeyPilot` entry under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`

## Notes

- A hold shortcut on a letter key sends that letter when you *release* it, not when you press it. You won't notice this
  while typing, but holding the key down no longer auto-repeats (`wwwww`).
- Hold shortcuts only fire when you press the key on its own, so `Ctrl+W` and `Shift+W` still work normally.
- Windows doesn't let a normal app see keys while an app running as administrator is focused. To use shortcuts there,
  run HotkeyPilot as administrator too.
