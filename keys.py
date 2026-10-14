"""Virtual-key names and helpers for describing shortcuts."""

MOD_ORDER = ["ctrl", "alt", "shift", "win"]

# Left/right modifier virtual-key codes (a low-level hook always reports these).
MOD_VKS = {
    0xA0: "shift", 0xA1: "shift", 0x10: "shift",
    0xA2: "ctrl", 0xA3: "ctrl", 0x11: "ctrl",
    0xA4: "alt", 0xA5: "alt", 0x12: "alt",
    0x5B: "win", 0x5C: "win",
}

_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x13: "Pause", 0x14: "CapsLock",
    0x1B: "Esc", 0x20: "Space", 0x21: "PageUp", 0x22: "PageDown", 0x23: "End",
    0x24: "Home", 0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0x2C: "PrintScreen", 0x2D: "Insert", 0x2E: "Delete", 0x5D: "Menu",
    0x90: "NumLock", 0x91: "ScrollLock",
    0xAD: "VolumeMute", 0xAE: "VolumeDown", 0xAF: "VolumeUp",
    0xB0: "MediaNext", 0xB1: "MediaPrev", 0xB2: "MediaStop", 0xB3: "MediaPlayPause",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`",
    0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
    0x6A: "Num*", 0x6B: "Num+", 0x6D: "Num-", 0x6E: "Num.", 0x6F: "Num/",
}
for _i in range(26):
    _NAMES[0x41 + _i] = chr(0x41 + _i)
for _i in range(10):
    _NAMES[0x30 + _i] = str(_i)
    _NAMES[0x60 + _i] = f"Num{_i}"
for _i in range(24):
    _NAMES[0x70 + _i] = f"F{_i + 1}"

_VKS = {name.lower(): vk for vk, name in _NAMES.items()}

# Keys that normally produce text; binding them without modifiers affects typing.
TYPING_VKS = (
    set(range(0x41, 0x5B)) | set(range(0x30, 0x3A)) | set(range(0x60, 0x6A))
    | {0x08, 0x09, 0x0D, 0x20, 0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF, 0xC0, 0xDB, 0xDC, 0xDD, 0xDE}
)


def vk_name(vk):
    return _NAMES.get(vk, f"VK{vk:02X}")


def name_to_vk(name):
    name = name.strip().lower()
    if name in _VKS:
        return _VKS[name]
    if name.startswith("vk"):
        return int(name[2:], 16)
    raise ValueError(f"Unknown key: {name}")


def sort_mods(mods):
    return [m for m in MOD_ORDER if m in mods]


def format_trigger(trigger):
    if not trigger or not trigger.get("key"):
        return "(not set)"
    parts = [m.capitalize() for m in sort_mods(trigger.get("modifiers", []))]
    keys = "+".join(parts + [trigger["key"]])
    if trigger.get("type") == "hold":
        return f"Hold {keys} for {trigger.get('seconds', 3):g}s"
    return keys


def trigger_signature(trigger):
    """Two shortcuts with the same signature would collide in the hook."""
    return (trigger["key"].lower(), tuple(sort_mods(trigger.get("modifiers", []))))
