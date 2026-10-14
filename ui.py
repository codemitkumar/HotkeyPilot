"""Settings window: list, add, edit and record shortcuts."""

import copy
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import storage
from actions import (ACTION_LABELS, ACTION_TYPES, BROWSERS, describe_action, installed_browsers,
                     list_start_apps, run_action)
from keys import MOD_VKS, TYPING_VKS, format_trigger, name_to_vk, sort_mods, trigger_signature, vk_name
from theme import C, FONT, apply_theme, style_window
from version import __version__

GAP = 24


def run_in_thread(widget, fn, done):
    """Run fn() in a worker thread and call done(result, error) back on the Tk thread."""
    box = {}

    def work():
        try:
            box["result"] = fn()
        except Exception as e:  # noqa: BLE001 - reported to the user
            box["error"] = e

    def poll():
        if t.is_alive():
            widget.after(80, poll)
        elif widget.winfo_exists():
            done(box.get("result"), box.get("error"))

    t = threading.Thread(target=work, daemon=True)
    t.start()
    poll()


def card(parent, **pack):
    frame = ttk.Frame(parent, padding=18)
    frame.pack(**pack)
    return frame


class AppPicker(tk.Toplevel):
    _cache = None

    def __init__(self, parent, on_pick):
        super().__init__(parent)
        self.title("Choose an app")
        self.transient(parent)
        self.geometry("440x560")
        style_window(self)
        self.on_pick = on_pick
        self.apps = []

        body = card(self, fill="both", expand=True, padx=GAP, pady=(GAP, 0))
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self._filter())
        entry = ttk.Entry(body, textvariable=self.search)
        entry.pack(fill="x", pady=(0, 12))
        entry.focus_set()

        frame = ttk.Frame(body)
        frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(frame, activestyle="none", borderwidth=0, highlightthickness=0,
                                  bg=C["card"], fg=C["text"], selectbackground=C["sel"],
                                  selectforeground="#ffffff", font=(FONT, 10))
        sb = ttk.Scrollbar(frame, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.listbox.bind("<Double-Button-1>", lambda e: self._choose())
        self.bind("<Return>", lambda e: self._choose())
        self.bind("<Escape>", lambda e: self.destroy())

        btns = ttk.Frame(self, style="Glass.TFrame")
        btns.pack(fill="x", padx=GAP, pady=16)
        ttk.Button(btns, text="Choose", style="Accent.TButton", command=self._choose).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=8)

        if AppPicker._cache is not None:
            self._loaded(AppPicker._cache, None)
        else:
            self.listbox.insert("end", "Loading installed apps…")
            run_in_thread(self, list_start_apps, self._loaded)

    def _loaded(self, apps, error):
        if error:
            self.listbox.delete(0, "end")
            self.listbox.insert("end", f"Could not list apps: {error}")
            return
        AppPicker._cache = apps
        self.apps = apps
        self._filter()

    def _filter(self):
        q = self.search.get().strip().lower()
        self.shown = [a for a in self.apps if q in a["Name"].lower()]
        self.listbox.delete(0, "end")
        for a in self.shown:
            self.listbox.insert("end", "  " + a["Name"])
        if self.shown:
            self.listbox.selection_set(0)

    def _choose(self):
        sel = self.listbox.curselection()
        if sel and self.shown:
            self.on_pick(self.shown[sel[0]])
            self.destroy()


class ShortcutDialog(tk.Toplevel):
    def __init__(self, app, shortcut=None):
        super().__init__(app.root)
        self.app = app
        sc = copy.deepcopy(shortcut) if shortcut else {
            "id": storage.new_id(), "name": "", "enabled": True,
            "trigger": {"type": "combo", "modifiers": [], "key": ""},
            "action": {"type": "app", "target": "", "label": ""},
        }
        self.sc = sc
        self.title("Edit shortcut" if shortcut else "New shortcut")
        self.transient(app.root)
        self.resizable(False, False)
        style_window(self)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.recording = False

        trig, act = sc["trigger"], sc["action"]
        self.name = tk.StringVar(value=sc.get("name", ""))
        self.trigger_type = tk.StringVar(value=trig.get("type", "combo"))
        # The recorded keys are shared, so switching between combo and hold keeps them.
        self.keys = {"modifiers": trig.get("modifiers", []), "key": trig.get("key", "")}
        self.hold_secs = tk.StringVar(value=f"{trig.get('seconds', 3):g}")
        self.action_type = tk.StringVar(value=ACTION_LABELS[act.get("type", "app")])
        self.target = tk.StringVar(value=act.get("target", ""))
        self.app_label = act.get("label", "")
        self.app_display = tk.StringVar(value=self.app_label)
        self.args = tk.StringVar(value=act.get("args", ""))
        self.browser_ids = installed_browsers()
        browser = act.get("browser", "default")
        if browser not in self.browser_ids:
            self.browser_ids.append(browser)
        self.browser = tk.StringVar(value=BROWSERS.get(browser, BROWSERS["default"])[0])
        self.private = tk.BooleanVar(value=act.get("private", False))
        self.new_window = tk.BooleanVar(value=act.get("new_window", False))

        ttk.Label(self, text=self.title(), style="Title.TLabel").pack(anchor="w", padx=GAP, pady=(20, 14))

        # --- Trigger card ---
        when = card(self, fill="x", padx=GAP)
        when.columnconfigure(0, weight=1)
        ttk.Label(when, text="TRIGGER", style="Caption.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        rb = ttk.Frame(when)
        rb.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 10))
        ttk.Radiobutton(rb, text="Key combination", value="combo", variable=self.trigger_type,
                        command=self._refresh).pack(side="left")
        ttk.Radiobutton(rb, text="Long press", value="hold", variable=self.trigger_type,
                        command=self._refresh).pack(side="left", padx=(20, 0))

        self.keys_label = ttk.Label(when, text="", style="Keycap.TLabel", width=24)
        self.keys_label.grid(row=2, column=0, sticky="we")
        self.record_btn = ttk.Button(when, text="Record", command=self._toggle_record, width=9)
        self.record_btn.grid(row=2, column=1, sticky="nse", padx=(10, 0))

        self.hold_row = ttk.Frame(when)
        self.hold_row.grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Label(self.hold_row, text="Hold for").pack(side="left")
        ttk.Spinbox(self.hold_row, from_=0.5, to=10, increment=0.5, width=5,
                    textvariable=self.hold_secs).pack(side="left", padx=8)
        ttk.Label(self.hold_row, text="seconds").pack(side="left")
        self.hint = ttk.Label(when, text="", style="Muted.TLabel", wraplength=440, justify="left")
        self.hint.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # --- Action card ---
        then = card(self, fill="x", padx=GAP, pady=(12, 0))
        then.columnconfigure(1, weight=1)
        ttk.Label(then, text="ACTION", style="Caption.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        cb = ttk.Combobox(then, state="readonly", textvariable=self.action_type,
                          values=[label for _, label in ACTION_TYPES])
        cb.grid(row=1, column=0, columnspan=3, sticky="we", pady=(6, 10))
        cb.bind("<<ComboboxSelected>>", lambda e: self._action_changed())

        self.target_label = ttk.Label(then, text="", style="Muted.TLabel", width=10)
        self.target_label.grid(row=2, column=0, sticky="w")
        self.target_entry = ttk.Entry(then, textvariable=self.target, width=36)
        self.target_entry.grid(row=2, column=1, sticky="we")
        self.browse_btn = ttk.Button(then, text="Browse", command=self._browse, width=9)
        self.browse_btn.grid(row=2, column=2, sticky="e", padx=(10, 0))

        self.args_label = ttk.Label(then, text="Arguments", style="Muted.TLabel")
        self.args_label.grid(row=3, column=0, sticky="w", pady=(10, 0))
        self.args_entry = ttk.Entry(then, textvariable=self.args)
        self.args_entry.grid(row=3, column=1, columnspan=2, sticky="we", pady=(10, 0))

        self.url_hint = ttk.Label(then, text="Add several sites separated by spaces, e.g.  youtube.com  gmail.com",
                                  style="Muted.TLabel")
        self.url_hint.grid(row=4, column=1, columnspan=2, sticky="w", pady=(6, 0))
        self.browser_label = ttk.Label(then, text="Browser", style="Muted.TLabel")
        self.browser_label.grid(row=5, column=0, sticky="w", pady=(10, 0))
        self.url_row = ttk.Frame(then)
        self.url_row.grid(row=5, column=1, columnspan=2, sticky="we", pady=(10, 0))
        ttk.Combobox(self.url_row, state="readonly", textvariable=self.browser, width=18,
                     values=[BROWSERS[b][0] for b in self.browser_ids]).pack(side="left")
        ttk.Checkbutton(self.url_row, text="Private", variable=self.private).pack(side="left", padx=(16, 0))
        ttk.Checkbutton(self.url_row, text="New window", variable=self.new_window).pack(side="left", padx=(16, 0))

        ttk.Label(then, text="Name", style="Muted.TLabel").grid(row=6, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(then, textvariable=self.name).grid(row=6, column=1, columnspan=2, sticky="we", pady=(10, 0))

        btns = ttk.Frame(self, style="Glass.TFrame")
        btns.pack(fill="x", padx=GAP, pady=18)
        ttk.Button(btns, text="Test", command=self._test).pack(side="left")
        ttk.Button(btns, text="Save", style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self._cancel).pack(side="right", padx=8)

        self.hold_secs.trace_add("write", lambda *_: self._refresh())
        self._action_changed(initial=True)
        self._refresh()
        self.grab_set()
        self.app.center(self)

    # ---- trigger ----
    def _current_trigger(self):
        if self.trigger_type.get() == "hold":
            try:
                secs = max(0.5, min(60.0, float(self.hold_secs.get())))
            except ValueError:
                secs = 3.0
            return {"type": "hold", "modifiers": sort_mods(self.keys["modifiers"]), "key": self.keys["key"],
                    "seconds": secs}
        return {"type": "combo", "modifiers": sort_mods(self.keys["modifiers"]), "key": self.keys["key"]}

    def _refresh(self):
        hold = self.trigger_type.get() == "hold"
        if self.recording:
            self.keys_label.configure(style="Recording.TLabel", text="Press your keys…")
        else:
            trig = self._current_trigger()
            self.keys_label.configure(style="Keycap.TLabel",
                                      text=format_trigger(trig) if trig["key"] else "—")
        if hold:
            self.hold_row.grid()
            self.hint.configure(text="Hold the key (or combination) down to run the action. "
                                     "A quick tap still works normally.")
        else:
            self.hold_row.grid_remove()
            self.hint.configure(text="Include Ctrl, Alt, Shift or Win so normal typing isn't blocked.")

    def _toggle_record(self):
        if self.recording:
            self._stop_record()
            return
        self.recording = True
        self.record_btn.configure(text="Stop")
        self.app.engine.start_recording(lambda vk, mods: self.app.post(self._recorded, vk, mods))
        self._refresh()

    def _stop_record(self):
        self.recording = False
        self.app.engine.cancel_recording()
        if self.winfo_exists():
            self.record_btn.configure(text="Record")
            self._refresh()

    def _recorded(self, vk, mods):
        if not self.winfo_exists():
            return
        self.recording = False
        self.record_btn.configure(text="Record")
        if vk is not None and vk not in MOD_VKS:
            self.keys = {"modifiers": sort_mods(mods), "key": vk_name(vk)}
        self._refresh()

    # ---- action ----
    def _action_kind(self):
        return next(k for k, label in ACTION_TYPES if label == self.action_type.get())

    def _action_changed(self, initial=False):
        kind = self._action_kind()
        if not initial:
            self.target.set("")
            self.args.set("")
            self.app_label = ""
            self.app_display.set("")
        labels = {"app": "App", "program": "File", "folder": "Folder", "url": "Websites", "command": "Command"}
        self.target_label.configure(text=labels[kind])
        if kind == "app":
            self.target_entry.configure(state="readonly", textvariable=self.app_display)
            self.browse_btn.configure(text="Choose")
            self.browse_btn.grid()
        else:
            self.target_entry.configure(state="normal", textvariable=self.target)
            self.browse_btn.configure(text="Browse")
            if kind in ("program", "folder"):
                self.browse_btn.grid()
            else:
                self.browse_btn.grid_remove()
        for widget in (self.args_label, self.args_entry):
            widget.grid() if kind == "program" else widget.grid_remove()
        for widget in (self.url_hint, self.browser_label, self.url_row):
            widget.grid() if kind == "url" else widget.grid_remove()

    def _browse(self):
        kind = self._action_kind()
        if kind == "app":
            AppPicker(self, self._picked_app)
        elif kind == "program":
            path = filedialog.askopenfilename(parent=self, title="Choose a program or file",
                                              filetypes=[("Programs", "*.exe *.bat *.cmd *.lnk"), ("All files", "*.*")])
            if path:
                self.target.set(path.replace("/", "\\"))
        elif kind == "folder":
            path = filedialog.askdirectory(parent=self, title="Choose a folder")
            if path:
                self.target.set(path.replace("/", "\\"))

    def _picked_app(self, app):
        self.target.set(app["AppID"])
        self.app_label = app["Name"]
        self.app_display.set(app["Name"])
        if not self.name.get().strip():
            self.name.set(app["Name"])

    def _current_action(self):
        act = {"type": self._action_kind(), "target": self.target.get().strip()}
        if act["type"] == "app":
            act["label"] = self.app_label
        if act["type"] == "program" and self.args.get().strip():
            act["args"] = self.args.get().strip()
        if act["type"] == "url":
            act["browser"] = next((b for b in self.browser_ids if BROWSERS[b][0] == self.browser.get()), "default")
            act["private"] = self.private.get()
            act["new_window"] = self.new_window.get()
        return act

    def _test(self):
        try:
            run_action(self._current_action())
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Test failed", str(e), parent=self)

    # ---- save ----
    def _save(self):
        trig, act = self._current_trigger(), self._current_action()
        if not trig["key"]:
            messagebox.showwarning("Missing shortcut", "Click Record and press the keys you want to use.", parent=self)
            return
        if not act["target"]:
            messagebox.showwarning("Missing action", "Choose what the shortcut should open or run.", parent=self)
            return
        if act["type"] == "url" and act["private"] and act["browser"] == "default":
            messagebox.showwarning("Pick a browser", "Choose a specific browser to open a private window.", parent=self)
            return
        sig = trigger_signature(trig)
        for other in self.app.shortcuts:
            if other["id"] != self.sc["id"] and trigger_signature(other["trigger"]) == sig:
                messagebox.showwarning("Already used", f"{format_trigger(other['trigger'])} is already used by "
                                       f"\"{other['name']}\".", parent=self)
                return
        if trig["type"] == "combo" and not trig["modifiers"] and name_to_vk(trig["key"]) in TYPING_VKS:
            if not messagebox.askyesno("Blocks typing", f"Using {trig['key']} on its own means you can no longer "
                                       f"type it anywhere while HotkeyPilot is running.\n\nUse it anyway?",
                                       parent=self):
                return
        self.sc["trigger"] = trig
        self.sc["action"] = act
        self.sc["name"] = self.name.get().strip() or describe_action(act)
        self._stop_record()
        self.app.save_shortcut(self.sc)
        self.destroy()

    def _cancel(self):
        self._stop_record()
        self.destroy()


class App:
    def __init__(self, engine, shortcuts, start_hidden=False, icon_image=None):
        self.engine = engine
        self.shortcuts = shortcuts
        self.tray = None
        self._q = queue.Queue()

        self.root = tk.Tk()
        self.root.title("HotkeyPilot")
        self.root.geometry("860x580")
        self.root.minsize(640, 400)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        if icon_image is not None:
            from PIL import ImageTk
            self._icon = ImageTk.PhotoImage(icon_image)
            self.root.iconphoto(True, self._icon)

        style_window(self.root)
        apply_theme(self.root)

        # Header (on glass)
        top = ttk.Frame(self.root, style="Glass.TFrame")
        top.pack(fill="x", padx=GAP, pady=(22, 16))
        heading = ttk.Frame(top, style="Glass.TFrame")
        heading.pack(side="left")
        ttk.Label(heading, text="Shortcuts", style="Title.TLabel").pack(anchor="w")
        ttk.Label(heading, text="Works anywhere in Windows, even when this window is closed.",
                  style="Sub.TLabel").pack(anchor="w")
        self.status = ttk.Label(top, text="", style="Pill.TLabel")
        self.status.pack(side="right", anchor="n", pady=(6, 0))

        # Footer + actions (packed bottom-up so they never get squeezed out)
        foot = ttk.Frame(self.root, padding=(18, 10))
        foot.pack(fill="x", side="bottom", padx=GAP, pady=(0, GAP))
        self.autostart = tk.BooleanVar(value=storage.get_autostart())
        ttk.Checkbutton(foot, text="Start with Windows", variable=self.autostart,
                        command=self._autostart_changed).pack(side="left")
        self.paused = tk.BooleanVar(value=engine.paused)
        ttk.Checkbutton(foot, text="Pause all", variable=self.paused,
                        command=lambda: self.set_paused(self.paused.get())).pack(side="left", padx=24)
        ttk.Label(foot, text=f"v{__version__}  ·  Double-click a row to edit", style="Muted.TLabel").pack(side="right")

        btns = ttk.Frame(self.root, style="Glass.TFrame")
        btns.pack(fill="x", side="bottom", padx=GAP, pady=12)
        ttk.Button(btns, text="+  New shortcut", style="Accent.TButton", command=self.add).pack(side="left")
        for text, cmd in (("Run", self.run_selected), ("Delete", self.delete),
                          ("On / Off", self.toggle), ("Edit", self.edit)):
            ttk.Button(btns, text=text, command=cmd).pack(side="right", padx=(8, 0))

        # List card
        mid = ttk.Frame(self.root, padding=(8, 6, 4, 6))
        mid.pack(fill="both", expand=True, padx=GAP)
        cols = ("on", "keys", "name", "action")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse")
        for col, text, width, stretch in (("on", "", 36, False), ("keys", "SHORTCUT", 190, False),
                                          ("name", "NAME", 160, True), ("action", "ACTION", 230, True)):
            self.tree.heading(col, text=text, anchor="w")
            self.tree.column(col, width=width, stretch=stretch, anchor="center" if col == "on" else "w")
        self.tree.tag_configure("on", foreground=C["text"])
        self.tree.tag_configure("off", foreground=C["dim"])
        sb = ttk.Scrollbar(mid, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-Button-1>", lambda e: self.edit())
        self.tree.bind("<Delete>", lambda e: self.delete())
        self.tree.bind("<space>", lambda e: self.toggle())

        self.refresh()
        self.root.after(50, self._drain)
        if start_hidden:
            self.root.withdraw()
        else:
            self.center(self.root)

    # ---- cross-thread plumbing ----
    def post(self, fn, *args):
        """Schedule fn(*args) on the Tk thread (safe to call from any thread)."""
        self._q.put((fn, args))

    def _drain(self):
        try:
            while True:
                fn, args = self._q.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.root.after(50, self._drain)

    # ---- window ----
    def center(self, win):
        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        x = (win.winfo_screenwidth() - w) // 2
        y = (win.winfo_screenheight() - h) // 3
        win.geometry(f"+{x}+{y}")

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(200, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def hide(self):
        self.root.withdraw()

    def quit(self):
        self.root.quit()

    def run(self):
        self.root.mainloop()

    # ---- data ----
    def refresh(self):
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for sc in self.shortcuts:
            on = sc.get("enabled", True)
            self.tree.insert("", "end", iid=sc["id"], tags=("on",) if on else ("off",),
                             values=("●" if on else "○", format_trigger(sc["trigger"]),
                                     sc.get("name", ""), describe_action(sc["action"])))
        if sel and self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])
        active = sum(1 for s in self.shortcuts if s.get("enabled", True))
        if self.engine.paused:
            self.status.configure(text="●  Paused", foreground=C["warn"])
        else:
            self.status.configure(text=f"●  Active · {active}", foreground=C["ok"])

    def _commit(self):
        storage.save_shortcuts(self.shortcuts)
        self.engine.set_shortcuts(self.shortcuts)
        self.refresh()

    def _selected(self):
        sel = self.tree.selection()
        return next((s for s in self.shortcuts if sel and s["id"] == sel[0]), None)

    def save_shortcut(self, sc):
        for i, s in enumerate(self.shortcuts):
            if s["id"] == sc["id"]:
                self.shortcuts[i] = sc
                break
        else:
            self.shortcuts.append(sc)
        self._commit()
        self.tree.selection_set(sc["id"])

    def add(self):
        ShortcutDialog(self)

    def edit(self):
        sc = self._selected()
        if sc:
            ShortcutDialog(self, sc)

    def toggle(self):
        sc = self._selected()
        if sc:
            sc["enabled"] = not sc.get("enabled", True)
            self._commit()

    def delete(self):
        sc = self._selected()
        if sc and messagebox.askyesno("Delete shortcut", f"Delete \"{sc['name']}\"?", parent=self.root):
            self.shortcuts.remove(sc)
            self._commit()

    def run_selected(self):
        sc = self._selected()
        if sc:
            try:
                run_action(sc["action"])
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Could not run", str(e), parent=self.root)

    def set_paused(self, paused):
        self.engine.paused = paused
        self.paused.set(paused)
        self.refresh()
        if self.tray:
            self.tray.update_menu()

    def _autostart_changed(self):
        try:
            storage.set_autostart(self.autostart.get())
        except OSError as e:
            messagebox.showerror("Start with Windows", str(e), parent=self.root)
            self.autostart.set(storage.get_autostart())
