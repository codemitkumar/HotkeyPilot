"""Global keyboard hook that detects key combos and press-and-hold shortcuts."""

import ctypes
import logging
import threading
import time
from ctypes import wintypes

from keys import MOD_VKS, name_to_vk, vk_name

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_QUIT = 0x12
WM_APP_REHOOK = 0x8001
REHOOK_SECONDS = 30  # Windows silently drops slow hooks; re-installing keeps us alive
LLKHF_EXTENDED = 0x01
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x1, 0x2
VK_MASK = 0xE8  # unassigned key, used to stop Win/Alt releases opening Start/menus
INJECT_MARKER = 0x484B5031  # tags our own injected events so the hook ignores them

MOD_CHECK = ((0xA2, "ctrl"), (0xA3, "ctrl"), (0xA0, "shift"), (0xA1, "shift"),
             (0xA4, "alt"), (0xA5, "alt"), (0x5B, "win"), (0x5C, "win"))


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


def _inject(vk, scan=0, flags=0, up=False):
    f = (KEYEVENTF_EXTENDEDKEY if flags & LLKHF_EXTENDED else 0) | (KEYEVENTF_KEYUP if up else 0)
    user32.keybd_event(vk, scan, f, INJECT_MARKER)


def _mask_menu_keys(mods):
    if "win" in mods or "alt" in mods:
        _inject(VK_MASK)
        _inject(VK_MASK, up=True)


class _PendingHold:
    def __init__(self, vk, scan, flags, shortcut):
        self.vk, self.scan, self.flags, self.shortcut = vk, scan, flags, shortcut
        self.fired = False
        self.timer = None


class HotkeyEngine:
    def __init__(self, on_trigger):
        self.on_trigger = on_trigger
        self.paused = False
        self._combos = {}  # (vk, frozenset(mods)) -> shortcut
        self._holds = {}   # (vk, frozenset(mods)) -> shortcut
        self._down = set()
        self._down_time = {}
        self._swallow_up = set()
        self._pending = None
        self._recorder = None
        self._lock = threading.Lock()
        self._thread = None
        self._thread_id = None
        self._proc_ref = None

    # ---- configuration -------------------------------------------------
    def set_shortcuts(self, shortcuts):
        combos, holds = {}, {}
        for sc in shortcuts:
            trig = sc.get("trigger") or {}
            if not sc.get("enabled", True) or not trig.get("key"):
                continue
            try:
                vk = name_to_vk(trig["key"])
            except ValueError:
                log.warning("Skipping shortcut with unknown key: %s", trig)
                continue
            key = (vk, frozenset(trig.get("modifiers", [])))
            if trig.get("type") == "hold":
                holds[key] = sc
            else:
                combos[key] = sc
        with self._lock:
            self._combos, self._holds = combos, holds

    def start_recording(self, callback):
        """callback(vk, mods) is called from the hook thread; vk=None means cancelled."""
        with self._lock:
            self._recorder = callback

    def cancel_recording(self):
        with self._lock:
            self._recorder = None

    # ---- lifecycle -----------------------------------------------------
    def start(self):
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(ready,), name="keyhook", daemon=True)
        self._thread.start()
        ready.wait(5)

    def stop(self):
        if getattr(self, "_stop_rehook", None):
            self._stop_rehook.set()
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def _install(self):
        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc_ref, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            log.error("SetWindowsHookEx failed: %s", ctypes.get_last_error())
        return hook

    def _rehook_timer(self):
        stop = threading.Event()
        self._stop_rehook = stop
        while not stop.wait(REHOOK_SECONDS):
            user32.PostThreadMessageW(self._thread_id, WM_APP_REHOOK, 0, 0)

    def _run(self, ready):
        self._thread_id = kernel32.GetCurrentThreadId()
        self._proc_ref = HOOKPROC(self._proc)
        # Make sure this thread has a message queue before anyone posts to it.
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        hook = self._install()
        if hook:
            log.info("Keyboard hook installed")
        ready.set()
        threading.Thread(target=self._rehook_timer, name="rehook", daemon=True).start()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_APP_REHOOK:
                fresh = self._install()  # install the new hook before removing the old one
                if fresh:
                    if hook:
                        user32.UnhookWindowsHookEx(hook)
                    hook = fresh
                continue
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if hook:
            user32.UnhookWindowsHookEx(hook)

    # ---- hook ----------------------------------------------------------
    def _proc(self, n_code, w_param, l_param):
        if n_code == 0:
            kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if kb.dwExtraInfo != INJECT_MARKER:
                try:
                    if self._handle(w_param in (WM_KEYDOWN, WM_SYSKEYDOWN), kb):
                        return 1
                except Exception:
                    log.exception("Error in keyboard hook")
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    @staticmethod
    def _mods():
        return frozenset(name for vk, name in MOD_CHECK if user32.GetAsyncKeyState(vk) & 0x8000)

    def _dispatch(self, shortcut):
        threading.Thread(target=self.on_trigger, args=(shortcut,), daemon=True).start()

    def _handle(self, is_down, kb):
        """Return True to block the key event from reaching other apps."""
        vk = kb.vkCode
        # Auto-repeat arrives every ~30-500 ms; an older "down" means we missed a key-up.
        repeat = is_down and vk in self._down and (kb.time - self._down_time.get(vk, 0)) & 0xFFFFFFFF < 1000
        if is_down:
            self._down.add(vk)
            self._down_time[vk] = kb.time
        else:
            self._down.discard(vk)

        if not is_down and vk in self._swallow_up:
            self._swallow_up.discard(vk)
            return True

        with self._lock:
            # Recording a new shortcut from the settings window.
            if self._recorder and is_down and vk not in MOD_VKS:
                cb, self._recorder = self._recorder, None
                mods = self._mods()
                _mask_menu_keys(mods)
                self._swallow_up.add(vk)
                cb(None if (vk == 0x1B and not mods) else vk, mods)
                return True

            if self._pending:
                return self._handle_pending(is_down, kb)

            if self.paused or self._recorder or not is_down:
                return False

            is_mod = vk in MOD_VKS
            mods = self._mods()

            # Start timing a press-and-hold shortcut. The key press is held back and
            # replayed if the key is released early, so normal typing still works.
            if not repeat and not is_mod and (vk, mods) in self._holds:
                p = _PendingHold(vk, kb.scanCode, kb.flags, self._holds[(vk, mods)])
                secs = float(p.shortcut["trigger"].get("seconds", 3))
                p.started = time.monotonic()
                log.info("Hold %s started (%gs needed)", vk_name(vk), secs)
                p.timer = threading.Timer(secs, self._hold_elapsed, args=(p,))
                p.timer.daemon = True
                self._pending = p
                p.timer.start()
                return True

            if not is_mod:
                sc = self._combos.get((vk, mods))
                if sc:
                    if not repeat:
                        _mask_menu_keys(mods)
                        self._dispatch(sc)
                    self._swallow_up.add(vk)
                    return True
        return False

    def _handle_pending(self, is_down, kb):
        p = self._pending
        if kb.vkCode == p.vk:
            if is_down:
                return True  # auto-repeat while holding
            self._pending = None
            p.timer.cancel()
            if not p.fired:  # tapped, not held: type the key after all
                log.info("Hold %s released after %.2fs, too short", vk_name(p.vk), time.monotonic() - p.started)
                _inject(p.vk, p.scan, p.flags)
                _inject(p.vk, p.scan, p.flags, up=True)
            return True
        if is_down and not p.fired:
            # Another key pressed mid-hold (fast typing): replay both in order.
            self._pending = None
            p.timer.cancel()
            log.info("Hold %s cancelled after %.2fs by %s (injected=%s, extra=%#x)", vk_name(p.vk),
                     time.monotonic() - p.started, vk_name(kb.vkCode), bool(kb.flags & 0x10), kb.dwExtraInfo)
            _inject(p.vk, p.scan, p.flags)
            _inject(kb.vkCode, kb.scanCode, kb.flags)
            return True
        return False

    def _hold_elapsed(self, p):
        with self._lock:
            if self._pending is not p or p.fired:
                return
            p.fired = True
        self._dispatch(p.shortcut)
