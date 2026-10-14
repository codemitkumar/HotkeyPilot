"""Dark-blue glass theme: acrylic blur behind the window, flat navy cards on top."""

import ctypes
import sys
from tkinter import ttk

FONT = "Segoe UI"

# Pixels painted in KEY become see-through, revealing the blurred acrylic backdrop.
KEY = "#010203"
C = {
    "base": "#0a1224",      # window background when blur isn't available
    "card": "#0f1a30",
    "field": "#16223d",
    "hover": "#1d2d50",
    "border": "#243556",
    "sel": "#1e3a6e",
    "text": "#e6edf7",
    "muted": "#8093b3",
    "dim": "#4f5f7d",
    "accent": "#3b82f6",
    "accent_hover": "#60a5fa",
    "ok": "#4ade80",
    "warn": "#fbbf24",
}
TINT_ABGR = 0xCC28140A  # acrylic tint: #0a1428 at ~80% opacity

_glass = None  # decided on the first window


class _AccentPolicy(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]


class _WinCompAttrData(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_size_t)]


def _hwnd(win):
    win.update_idletasks()
    return ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()


def _enable_acrylic(hwnd):
    if sys.getwindowsversion().build < 17763:
        return False
    try:
        policy = _AccentPolicy(4, 2, TINT_ABGR, 0)  # ACCENT_ENABLE_ACRYLICBLURBEHIND
        data = _WinCompAttrData(19, ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p), ctypes.sizeof(policy))
        return bool(ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data)))
    except Exception:
        return False


def style_window(win):
    """Dark title bar plus blue acrylic glass for a Tk or Toplevel window."""
    global _glass
    hwnd = _hwnd(win)
    try:
        on = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (newer, older builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), 4) == 0:
                break
    except Exception:
        pass
    ok = _enable_acrylic(hwnd) if _glass is not False else False
    if _glass is None:
        _glass = ok
    if _glass:
        win.configure(bg=KEY)
        win.attributes("-transparentcolor", KEY)
    else:
        win.configure(bg=C["base"])


def glass_bg():
    return KEY if _glass else C["base"]


def apply_theme(root):
    """Call once, after style_window(root)."""
    g = glass_bg()
    card, field, border = C["card"], C["field"], C["border"]
    s = ttk.Style(root)
    s.theme_use("clam")

    s.configure(".", background=card, foreground=C["text"], fieldbackground=field,
                bordercolor=border, lightcolor=field, darkcolor=field, troughcolor=card,
                selectbackground=C["accent"], selectforeground="#ffffff", insertcolor=C["text"],
                focuscolor=C["accent"], arrowcolor=C["muted"], font=(FONT, 10))

    # Surfaces
    s.configure("TFrame", background=card)
    s.configure("Glass.TFrame", background=g)
    s.configure("TLabel", background=card, foreground=C["text"])
    s.configure("Muted.TLabel", background=card, foreground=C["muted"], font=(FONT, 9))
    s.configure("Caption.TLabel", background=card, foreground=C["muted"], font=(FONT, 8, "bold"))
    s.configure("Title.TLabel", background=g, foreground=C["text"], font=(FONT + " Semibold", 20))
    s.configure("Sub.TLabel", background=g, foreground=C["muted"], font=(FONT, 10))
    s.configure("Pill.TLabel", background=card, font=(FONT + " Semibold", 9), padding=(12, 5))
    s.configure("Keycap.TLabel", background=field, foreground=C["text"],
                font=(FONT + " Semibold", 14), padding=(16, 12), anchor="center")
    s.configure("Recording.TLabel", background=field, foreground=C["accent_hover"],
                font=(FONT + " Semibold", 12), padding=(16, 12), anchor="center")
    s.configure("TSeparator", background=border)

    # Buttons (flat, no focus ring)
    s.layout("TButton", [("Button.border", {"sticky": "nswe", "border": "1", "children": [
        ("Button.padding", {"sticky": "nswe", "children": [("Button.label", {"sticky": "nswe"})]})]})])
    s.configure("TButton", background=field, foreground=C["text"], bordercolor=field,
                lightcolor=field, darkcolor=field, padding=(16, 8), relief="flat", anchor="center")
    s.map("TButton", background=[("pressed", border), ("active", C["hover"])],
          bordercolor=[("active", C["hover"])], lightcolor=[("active", C["hover"])],
          darkcolor=[("active", C["hover"])])
    a, ah = C["accent"], C["accent_hover"]
    s.configure("Accent.TButton", background=a, foreground="#ffffff", bordercolor=a, lightcolor=a,
                darkcolor=a, font=(FONT + " Semibold", 10))
    s.map("Accent.TButton", background=[("pressed", a), ("active", ah)], bordercolor=[("active", ah)],
          lightcolor=[("active", ah)], darkcolor=[("active", ah)])

    # Inputs
    for style in ("TEntry", "TCombobox", "TSpinbox"):
        s.configure(style, fieldbackground=field, background=field, foreground=C["text"],
                    bordercolor=field, lightcolor=field, darkcolor=field, padding=7,
                    arrowcolor=C["muted"], insertcolor=C["text"])
        s.map(style, bordercolor=[("focus", a)], lightcolor=[("focus", a)],
              fieldbackground=[("readonly", field)], background=[("active", C["hover"])],
              arrowcolor=[("active", C["text"])])
    s.map("TCombobox", selectbackground=[("readonly", field)], selectforeground=[("readonly", C["text"])])
    root.option_add("*TCombobox*Listbox.background", field)
    root.option_add("*TCombobox*Listbox.foreground", C["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", a)
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    root.option_add("*TCombobox*Listbox.borderWidth", 0)
    root.option_add("*TCombobox*Listbox.font", (FONT, 10))

    for style in ("TRadiobutton", "TCheckbutton"):
        s.configure(style, background=card, foreground=C["text"], indicatorbackground=field,
                    indicatorforeground="#ffffff", upperbordercolor=border, lowerbordercolor=border,
                    indicatormargin=(0, 0, 8, 0), padding=(0, 4), focuscolor=card)
        s.map(style, background=[("active", card)],
              indicatorbackground=[("selected", a), ("active", C["hover"])])

    # List
    s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    s.configure("Treeview", background=card, fieldbackground=card, foreground=C["text"],
                bordercolor=card, lightcolor=card, darkcolor=card, rowheight=40, font=(FONT, 10))
    s.map("Treeview", background=[("selected", C["sel"])], foreground=[("selected", "#ffffff")])
    s.configure("Treeview.Heading", background=card, foreground=C["muted"], relief="flat",
                bordercolor=card, lightcolor=card, darkcolor=card, font=(FONT, 8, "bold"), padding=(10, 8))
    s.map("Treeview.Heading", background=[("active", card)])

    # Slim scrollbar without arrows
    s.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
        ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    s.configure("Vertical.TScrollbar", troughcolor=card, background=border, bordercolor=card,
                lightcolor=border, darkcolor=border, gripcount=0, arrowsize=8)
    s.map("Vertical.TScrollbar", background=[("active", C["dim"])])
