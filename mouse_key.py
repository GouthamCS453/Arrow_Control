import sys
import json
import os
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from pynput import mouse, keyboard
from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, KeyCode, Controller as KbController


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — CONFIGURATION  (Feature A: Editable Speed Settings)
#
#   config.json is auto-created next to this script on first run.
#   Users can edit the file in any text editor, or use the Settings window
#   (right-click the floating widget).
#   Changes made in the Settings window take effect immediately without restart.
# ══════════════════════════════════════════════════════════════════════════════

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

_CONFIG_DEFAULTS = {
    "min_speed":  3,    # Pixels per tick at the start of a key press
    "max_speed":  16,   # Pixels per tick at full ramp speed
    "ramp_time":  0.5,  # Seconds to ramp from min to max speed
}

def _load_config() -> dict:
    """Load config.json. Create it with defaults if it does not exist."""
    if not os.path.exists(_CONFIG_PATH):
        _save_config(_CONFIG_DEFAULTS.copy())
        print(f"[Config] Created default config: {_CONFIG_PATH}")
    try:
        with open(_CONFIG_PATH, "r") as f:
            data = json.load(f)
        # Fill in any missing keys with defaults (forward-compat)
        for k, v in _CONFIG_DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except Exception as e:
        print(f"[Config] Failed to read config, using defaults: {e}")
        return _CONFIG_DEFAULTS.copy()

def _save_config(cfg: dict):
    """Write the config dict back to config.json."""
    try:
        with open(_CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=4)
    except Exception as e:
        print(f"[Config] Failed to save config: {e}")

# Live config dict — all speed reads use this at runtime
CONFIG = _load_config()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — FIXED CONSTANTS  (not user-facing settings)
# ══════════════════════════════════════════════════════════════════════════════

TICK_RATE     = 0.016   # ~60 ticks/sec — movement loop interval
SCROLL_AMOUNT = 3       # Scroll lines per keypress


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — KEY MAPPINGS
#
#   Add or change key assignments here.  All new keys from Features B and C
#   are defined in this single place so they are easy to locate and modify.
# ══════════════════════════════════════════════════════════════════════════════

MOVE_KEYS = {
    Key.up:    ( 0, -1),
    Key.down:  ( 0,  1),
    Key.left:  (-1,  0),
    Key.right: ( 1,  0),
}

# ── Action keys ───────────────────────────────────────────────────────────────
SELECT_KEY    = KeyCode.from_char('e')   # Hold + Arrow  → drag / select
LCLICK_KEY    = KeyCode.from_char('a')   # Left click
RCLICK_KEY    = KeyCode.from_char('d')   # Right click
DBL_CLICK_KEY = KeyCode.from_char('z')   # Double left click       (Feature B)
MID_CLICK_KEY = KeyCode.from_char('q')   # Middle click            (Feature B)
SCROLL_UP     = KeyCode.from_char('w')   # Scroll up
SCROLL_DOWN   = KeyCode.from_char('s')   # Scroll down

# ── Speed modifier keys (read inside get_step) ────────────────────────────────
PRECISION_KEY = Key.shift                # Hold → slow / precise movement
TURBO_KEY     = Key.ctrl_l              # Hold → fast / turbo movement

# ── Global hotkeys ────────────────────────────────────────────────────────────
TOGGLE_KEY    = Key.f2
QUIT_KEY      = Key.f4
MOMENTARY_KEY = Key.scroll_lock         # Hold -> temporary mouse mode (Feature C)

# Keys whose press events are consumed (suppressed) when the controller is ON
OWNED_KEYS = set(MOVE_KEYS.keys()) | {
    SELECT_KEY, LCLICK_KEY, RCLICK_KEY,
    DBL_CLICK_KEY, MID_CLICK_KEY,          # Feature B
    SCROLL_UP, SCROLL_DOWN,
}


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — SHARED STATE
# ══════════════════════════════════════════════════════════════════════════════

mouse_ctrl = MouseController()
kb_ctrl    = KbController()

enabled  = True    # Latch state: True = mouse-key mode ON
running  = True    # Set False to shut down all threads

pressed   = set()  # Keys currently held (tracked only when enabled)
key_times = {}     # Maps held key → time.monotonic() it was first pressed
lock      = threading.Lock()

root: tk.Tk | None = None

_active_listener: keyboard.Listener | None = None
_listener_lock = threading.Lock()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — SPEED / RAMP ENGINE  (Feature A: Smooth Ramp)
#
#   Replaces the old abrupt two-speed (base / accelerated) model.
#   Speed increases linearly from min_speed to max_speed over ramp_time
#   seconds.  Optional Shift (precision) and Ctrl (turbo) modifiers are
#   applied as multipliers on top of the ramped value.
#
#   Formula:
#       progress = clamp(held_time / ramp_time, 0.0, 1.0)
#       speed    = min_speed + (max_speed - min_speed) * progress
#
#   Computational cost: 4 arithmetic ops per moving key per tick — negligible.
# ══════════════════════════════════════════════════════════════════════════════

def get_step(key) -> float:
    """Return the current pixel step for a held movement key."""
    held_time = time.monotonic() - key_times.get(key, time.monotonic())
    progress  = min(1.0, held_time / max(CONFIG["ramp_time"], 0.01))
    speed     = CONFIG["min_speed"] + (CONFIG["max_speed"] - CONFIG["min_speed"]) * progress

    # Speed modifiers — checked against the shared pressed set
    with lock:
        shift_held = PRECISION_KEY in pressed or Key.shift_r in pressed
        ctrl_held  = TURBO_KEY in pressed or Key.ctrl_r in pressed

    if shift_held:
        speed *= 0.3   # Precision / sniper
    elif ctrl_held:
        speed *= 2.5   # Turbo / sweep

    return speed

def active_move_keys():
    """Return list of movement keys currently in the pressed set."""
    return [k for k in MOVE_KEYS if k in pressed]


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — KEY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def re_emit_press(key):
    try: kb_ctrl.press(key)
    except Exception: pass

def re_emit_release(key):
    try: kb_ctrl.release(key)
    except Exception: pass

# Virtual-keycode → Key enum map for arrow keys (handles Windows extended VKs)
_ARROW_VK = {
    Key.up.value.vk    if hasattr(Key.up.value,    'vk') else None: Key.up,
    Key.down.value.vk  if hasattr(Key.down.value,  'vk') else None: Key.down,
    Key.left.value.vk  if hasattr(Key.left.value,  'vk') else None: Key.left,
    Key.right.value.vk if hasattr(Key.right.value, 'vk') else None: Key.right,
}
_ARROW_VK = {k: v for k, v in _ARROW_VK.items() if k is not None}

def _canonical(key):
    """Normalise a key to its Key enum if it is an arrow key, else return as-is."""
    if key in MOVE_KEYS:
        return key
    vk = getattr(key, 'vk', None)
    if vk and vk in _ARROW_VK:
        return _ARROW_VK[vk]
    return key


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — LISTENER MANAGEMENT
#
#   Three listeners cover three modes:
#     • Enabled  (suppress=True)  — intercepts owned keys, re-emits the rest
#     • Disabled (suppress=False) — passes all keys through; only watches F2/F4
#                                   and Caps Lock (Feature C: momentary mode)
# ══════════════════════════════════════════════════════════════════════════════

def _stop_active_listener():
    global _active_listener
    with _listener_lock:
        if _active_listener is not None:
            try:
                _active_listener.stop()
            except Exception:
                pass
            _active_listener = None

def _start_enabled_listener():
    """suppress=True listener — intercepts owned keys, re-emits the rest."""
    global _active_listener
    _stop_active_listener()
    lst = keyboard.Listener(
        on_press=_on_press_enabled,
        on_release=_on_release_enabled,
        suppress=True,
    )
    with _listener_lock:
        _active_listener = lst
    lst.start()

def _start_disabled_listener():
    """suppress=False listener — keyboard is fully normal.
    Monitors F2 / F4 for latch toggle/exit, and Caps Lock for momentary mode.
    """
    global _active_listener
    _stop_active_listener()
    lst = keyboard.Listener(
        on_press=_on_press_disabled,
        on_release=_on_release_disabled,   # Feature C: release Caps Lock
        suppress=False,
    )
    with _listener_lock:
        _active_listener = lst
    lst.start()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — LATCH TOGGLE & EXIT
# ══════════════════════════════════════════════════════════════════════════════

def do_toggle():
    """Toggle the latch state between enabled and disabled."""
    global enabled
    enabled = not enabled
    label = "ENABLED ✓" if enabled else "DISABLED ✗"
    print(f"[Arrow Mouse] {label}")

    with lock:
        pressed.clear()
        key_times.clear()

    if enabled:
        _start_enabled_listener()
    else:
        _start_disabled_listener()

    if root is not None:
        root.after(0, refresh_button)

def do_exit():
    global running
    running = False
    _stop_active_listener()
    if root is not None:
        root.after(0, root.destroy)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — ENABLED LISTENER CALLBACKS  (suppress=True)
#
#   Features B keys (Z, Q) are handled here alongside the existing A/D/W/S.
#   Shift and Ctrl are tracked in the pressed set so get_step() can read them.
# ══════════════════════════════════════════════════════════════════════════════

def _on_press_enabled(key):
    key = _canonical(key)

    if key == QUIT_KEY:
        do_exit()
        return False

    if key == TOGGLE_KEY:
        threading.Thread(target=do_toggle, daemon=True).start()
        return

    # Track modifier keys in the pressed set so get_step() sees them
    if key in (PRECISION_KEY, Key.shift_r, TURBO_KEY, Key.ctrl_r):
        with lock:
            pressed.add(key)
        return   # re-emit so other apps still receive Shift/Ctrl

    # Non-owned keys — pass through to OS
    if key not in OWNED_KEYS:
        re_emit_press(key)
        return

    # Register held key (idempotent — ignore repeat events)
    with lock:
        if key not in pressed:
            pressed.add(key)
            key_times[key] = time.monotonic()

    # Read drag state once
    with lock:
        select_held = SELECT_KEY in pressed

    # ── Single-fire click / scroll actions ───────────────────────────────────

    if key == LCLICK_KEY:
        if not select_held:
            mouse_ctrl.click(Button.left)
            print("[Click] Left")
        return

    if key == RCLICK_KEY:
        if not select_held:
            mouse_ctrl.click(Button.right)
            print("[Click] Right")
        return

    # ── Feature B: Double-click ───────────────────────────────────────────────
    if key == DBL_CLICK_KEY:
        if not select_held:
            mouse_ctrl.click(Button.left, 2)
            print("[Click] Double Left")
        return

    # ── Feature B: Middle-click ───────────────────────────────────────────────
    if key == MID_CLICK_KEY:
        if not select_held:
            mouse_ctrl.click(Button.middle)
            print("[Click] Middle")
        return

    if key == SCROLL_UP:
        mouse_ctrl.scroll(0,  SCROLL_AMOUNT); print("[Scroll] Up");   return
    if key == SCROLL_DOWN:
        mouse_ctrl.scroll(0, -SCROLL_AMOUNT); print("[Scroll] Down"); return

    # Arrow keys + SELECT_KEY are handled continuously by move_loop


def _on_release_enabled(key):
    key = _canonical(key)

    # Release tracked modifier keys
    if key in (PRECISION_KEY, Key.shift_r, TURBO_KEY, Key.ctrl_r):
        with lock:
            pressed.discard(key)
        return

    if key not in OWNED_KEYS:
        re_emit_release(key)
        return

    with lock:
        pressed.discard(key)
        key_times.pop(key, None)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — DISABLED LISTENER CALLBACKS  (suppress=False)
#
#   Feature C: Momentary Mode
#   When the controller is latched OFF, holding MOMENTARY_KEY (Caps Lock)
#   temporarily activates mouse-key mode.  Releasing it returns to normal.
#   The latch state (enabled) is NOT changed — F2 still works independently.
# ══════════════════════════════════════════════════════════════════════════════

_momentary_active = False   # True only while Caps Lock is physically held

def _on_press_disabled(key):
    """Only F2, F4, and Caps Lock are acted on; everything else goes to the OS."""
    global _momentary_active

    if key == QUIT_KEY:
        do_exit()
        return False

    if key == TOGGLE_KEY:
        threading.Thread(target=do_toggle, daemon=True).start()
        return

    # Feature C: start momentary mouse mode on Caps Lock press
    if key == MOMENTARY_KEY and not _momentary_active:
        _momentary_active = True
        print("[Momentary] Mouse mode active (Scroll Lock held)")
        _start_enabled_listener()

def _on_release_disabled(key):
    """Deactivate momentary mode when Caps Lock is released."""
    global _momentary_active

    if key == MOMENTARY_KEY and _momentary_active:
        _momentary_active = False
        print("[Momentary] Mouse mode released")
        with lock:
            pressed.clear()
            key_times.clear()
        _start_disabled_listener()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11 — MOVEMENT LOOP  (unchanged from original)
#
#   Runs at ~60 Hz.  Reads the pressed set and calls mouse_ctrl.move().
#   get_step() now returns a smoothly ramped value (Feature A) instead of
#   the old two-speed step.
# ══════════════════════════════════════════════════════════════════════════════

def move_loop():
    drag_active = False
    while running:
        time.sleep(TICK_RATE)

        if not enabled and not _momentary_active:
            if drag_active:
                try: mouse_ctrl.release(Button.left)
                except Exception: pass
                drag_active = False
            continue

        with lock:
            dirs        = active_move_keys()
            select_held = SELECT_KEY in pressed

        if not dirs:
            if drag_active:
                try: mouse_ctrl.release(Button.left)
                except Exception: pass
                drag_active = False
                print("[Select] Drag ended")
            continue

        # Manage drag state
        if select_held and not drag_active:
            try:
                mouse_ctrl.press(Button.left)
                drag_active = True
                print("[Select] Drag started")
            except Exception:
                pass
        elif not select_held and drag_active:
            try:
                mouse_ctrl.release(Button.left)
                drag_active = False
                print("[Select] Drag ended")
            except Exception:
                pass

        # Compute movement with smooth-ramped speed (Feature A)
        dx = dy = 0.0
        for k in dirs:
            vx, vy = MOVE_KEYS[k]
            s = get_step(k)
            dx += vx * s
            dy += vy * s

        if dx != 0 and dy != 0:   # Normalise diagonal speed
            dx *= 0.7071
            dy *= 0.7071

        try:
            mouse_ctrl.move(int(dx), int(dy))
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 12 — SETTINGS WINDOW  (Feature A: Editable Speed Config)
#
#   A plain Tk Toplevel with three labelled Entry fields.
#   Right-click the floating widget to open it.
#   "Save" writes to config.json and updates the live CONFIG dict immediately.
#   "Exit Program" calls do_exit() (replaces old right-click-to-exit).
# ══════════════════════════════════════════════════════════════════════════════

_settings_win: tk.Toplevel | None = None

def open_settings():
    global _settings_win

    # Only one settings window at a time
    if _settings_win is not None:
        try:
            _settings_win.lift()
            return
        except Exception:
            _settings_win = None

    win = tk.Toplevel(root)
    win.title("Speed Settings")
    win.resizable(False, False)
    win.attributes("-topmost", True)
    _settings_win = win

    def on_close():
        global _settings_win
        _settings_win = None
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)

    # ── Labels and Entry fields ───────────────────────────────────────────────
    fields = [
        ("Min Speed  (px/tick):", "min_speed"),
        ("Max Speed  (px/tick):", "max_speed"),
        ("Ramp Time  (seconds):", "ramp_time"),
    ]

    entries = {}
    for row, (label_text, key) in enumerate(fields):
        tk.Label(win, text=label_text, anchor="w").grid(
            row=row, column=0, padx=10, pady=6, sticky="w")
        var = tk.StringVar(value=str(CONFIG[key]))
        e = tk.Entry(win, textvariable=var, width=8)
        e.grid(row=row, column=1, padx=10, pady=6)
        entries[key] = var

    tk.Label(win, text="Shift = 0.3× speed  |  Ctrl = 2.5× speed",
             fg="gray", font=("TkDefaultFont", 8)).grid(
        row=len(fields), column=0, columnspan=2, pady=(0, 6))

    # ── Status label for feedback ─────────────────────────────────────────────
    status_var = tk.StringVar(value="")
    tk.Label(win, textvariable=status_var, fg="green").grid(
        row=len(fields)+1, column=0, columnspan=2)

    # ── Save button ───────────────────────────────────────────────────────────
    def do_save():
        try:
            new_min  = float(entries["min_speed"].get())
            new_max  = float(entries["max_speed"].get())
            new_ramp = float(entries["ramp_time"].get())
        except ValueError:
            status_var.set("Invalid values — use numbers only.")
            return

        if new_min <= 0 or new_max <= 0 or new_ramp <= 0:
            status_var.set("All values must be greater than 0.")
            return
        if new_min >= new_max:
            status_var.set("Max speed must be greater than min speed.")
            return

        CONFIG["min_speed"]  = new_min
        CONFIG["max_speed"]  = new_max
        CONFIG["ramp_time"]  = new_ramp
        _save_config(CONFIG)
        status_var.set("Saved! Changes active immediately.")
        print(f"[Config] Saved: min={new_min}, max={new_max}, ramp={new_ramp}s")

    tk.Button(win, text="Save", width=10, command=do_save).grid(
        row=len(fields)+2, column=0, pady=8, padx=10)

    # ── Exit program button ───────────────────────────────────────────────────
    tk.Button(win, text="Exit Program", width=12,
              command=do_exit).grid(
        row=len(fields)+2, column=1, pady=8, padx=10)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 13 — FLOATING WIDGET  (Feature D: Hover Cheat-Sheet)
#
#   The widget now supports two heights:
#     BTN_H_COLLAPSED = 48   — compact pill, always visible
#     BTN_H_EXPANDED  = 210  — full cheat-sheet revealed on hover
#
#   Hover <Enter>  → expand window + redraw with cheat-sheet
#   Hover <Leave>  → collapse window + redraw compact pill
#   Left-click     → toggle (latch ON/OFF)  [unchanged]
#   Right-click    → open Settings window   [changed from exit]
# ══════════════════════════════════════════════════════════════════════════════

BTN_W           = 210
BTN_H_COLLAPSED = 48
BTN_H_EXPANDED  = 210

ON_BG  = "#1DB954"
OFF_BG = "#3A3A4A"
ON_FG  = "#FFFFFF"
OFF_FG = "#AAAACC"

_drag_x = _drag_y = 0
_dragged = False
_widget_expanded = False


def build_toggle_window():
    global root

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.92)

    sw = root.winfo_screenwidth()
    root.geometry(f"{BTN_W}x{BTN_H_COLLAPSED}+{sw - BTN_W - 20}+20")

    root.canvas = tk.Canvas(root, width=BTN_W, height=BTN_H_COLLAPSED,
                            highlightthickness=0, bd=0)
    root.canvas.pack(fill="both", expand=True)

    _draw_widget(expanded=False)

    root.canvas.bind("<ButtonPress-1>",   _on_drag_start)
    root.canvas.bind("<B1-Motion>",       _on_drag_move)
    root.canvas.bind("<ButtonRelease-1>", _on_click_or_release)
    root.canvas.bind("<ButtonPress-3>",   lambda e: open_settings())  # Feature A
    root.canvas.bind("<Enter>",           _on_hover_enter)             # Feature D
    root.canvas.bind("<Leave>",           _on_hover_leave)             # Feature D

    root.mainloop()


# ── Drawing ───────────────────────────────────────────────────────────────────

def _draw_widget(expanded: bool = False):
    """Draw the compact pill, or the pill + cheat-sheet when expanded."""
    c   = root.canvas
    bg  = ON_BG  if enabled else OFF_BG
    fg  = ON_FG  if enabled else OFF_FG
    txt = "Mouse Keys  ON" if enabled else "Mouse Keys  OFF"

    h = BTN_H_EXPANDED if expanded else BTN_H_COLLAPSED

    root.configure(bg=bg)
    c.configure(bg=bg, height=h)
    c.delete("all")

    # ── Pill shape (top 48px) ─────────────────────────────────────────────────
    r = BTN_H_COLLAPSED // 2
    c.create_arc(0, 0, r*2, BTN_H_COLLAPSED, start=90, extent=180, fill=bg, outline=bg)
    c.create_arc(BTN_W - r*2, 0, BTN_W, BTN_H_COLLAPSED, start=270, extent=180, fill=bg, outline=bg)
    c.create_rectangle(r, 0, BTN_W - r, BTN_H_COLLAPSED, fill=bg, outline=bg)

    hl  = "#3de87a" if enabled else "#5a5a72"
    dot = "#AAFFBB" if enabled else "#888899"
    c.create_line(r, 3, BTN_W - r, 3, fill=hl, width=1)
    c.create_oval(14, BTN_H_COLLAPSED//2 - 5, 24, BTN_H_COLLAPSED//2 + 5,
                  fill=dot, outline="")

    try:
        fnt      = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        hint_fnt = tkfont.Font(family="Segoe UI", size=7)
    except Exception:
        fnt      = ("TkDefaultFont", 10, "bold")
        hint_fnt = ("TkDefaultFont", 7)

    c.create_text(BTN_W // 2 + 8, BTN_H_COLLAPSED // 2 - 4,
                  text=txt, fill=fg, font=fnt, anchor="center")

    hint_fg = "#88aa88" if enabled else "#666688"
    if not expanded:
        c.create_text(BTN_W // 2 + 8, BTN_H_COLLAPSED - 8,
                      text="F2 toggle · right-click settings · F4 exit",
                      fill=hint_fg, font=hint_fnt, anchor="center")

    # ── Feature D: Cheat-sheet (shown only when expanded) ─────────────────────
    if expanded:
        c.create_rectangle(0, BTN_H_COLLAPSED, BTN_W, BTN_H_EXPANDED,
                           fill=bg, outline=bg)
        c.create_line(10, BTN_H_COLLAPSED + 2, BTN_W - 10, BTN_H_COLLAPSED + 2,
                      fill=hl, width=1)

        try:
            cs_fnt = tkfont.Font(family="Segoe UI", size=8)
        except Exception:
            cs_fnt = ("TkDefaultFont", 8)

        # Two-column cheat sheet lines: left-side key, right-side action
        cheat_lines = [
            ("↑ ↓ ← →",   "Move pointer"),
            ("A",          "Left click"),
            ("Z",          "Double click"),
            ("D",          "Right click"),
            ("Q",          "Middle click"),
            ("W / S",      "Scroll up / down"),
            ("E + Arrow",  "Drag / select"),
            ("Scroll Lock",  "Momentary mouse"),
            ("Shift",      "Precision (slow)"),
            ("Ctrl",       "Turbo (fast)"),
            ("F2",         "Toggle ON / OFF"),
            ("F4",         "Exit"),
        ]

        y = BTN_H_COLLAPSED + 12
        for keys_str, action_str in cheat_lines:
            c.create_text(14, y, text=keys_str, fill=fg, font=cs_fnt, anchor="w")
            c.create_text(BTN_W - 10, y, text=action_str, fill=fg,
                          font=cs_fnt, anchor="e")
            y += 13


def refresh_button():
    """Redraw the widget in its current expanded/collapsed state."""
    if root:
        _draw_widget(expanded=_widget_expanded)


# ── Hover expand / collapse (Feature D) ──────────────────────────────────────

def _on_hover_enter(event):
    global _widget_expanded
    _widget_expanded = True
    root.geometry(f"{BTN_W}x{BTN_H_EXPANDED}")
    _draw_widget(expanded=True)

def _on_hover_leave(event):
    global _widget_expanded
    _widget_expanded = False
    root.geometry(f"{BTN_W}x{BTN_H_COLLAPSED}")
    _draw_widget(expanded=False)


# ── Drag (widget repositioning) ───────────────────────────────────────────────

def _on_drag_start(event):
    global _drag_x, _drag_y, _dragged
    _drag_x  = event.x_root - root.winfo_x()
    _drag_y  = event.y_root - root.winfo_y()
    _dragged = False

def _on_drag_move(event):
    global _dragged
    _dragged = True
    root.geometry(f"+{event.x_root - _drag_x}+{event.y_root - _drag_y}")

def _on_click_or_release(event):
    if not _dragged:
        threading.Thread(target=do_toggle, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 14 — ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 56)
    print("  Arrow Key Mouse Controller")
    print("=" * 56)
    print("  [Up][Dn][Lt][Rt]  Move pointer")
    print("  A                 Left click")
    print("  Z                 Double click             [NEW]")
    print("  D                 Right click")
    print("  Q                 Middle click             [NEW]")
    print("  W / S             Scroll up / down")
    print("  E + Arrow         Click-drag / select")
    print("  Shift             Precision (slow) mode    [NEW]")
    print("  Ctrl              Turbo (fast) mode        [NEW]")
    print("  Scroll Lock       Momentary mouse hold     [NEW]")
    print("  F2                Toggle ON / OFF")
    print("  F4                Exit program")
    print("=" * 56)
    print("  Floating widget:")
    print("    Hover         -> show full key guide  [NEW]")
    print("    Left-click    -> toggle ON / OFF")
    print("    Drag          -> reposition widget")
    print("    Right-click   -> open speed settings  [NEW]")
    print("=" * 56)
    print(f"  Config file: {_CONFIG_PATH}")
    print(f"  Current speed: min={CONFIG['min_speed']} "
          f"max={CONFIG['max_speed']} ramp={CONFIG['ramp_time']}s")
    print("=" * 56)

    threading.Thread(target=move_loop, daemon=True).start()
    _start_enabled_listener()

    # Tkinter must run on the main thread
    build_toggle_window()

    print("\n[Arrow Mouse] Exited. Goodbye!")


if __name__ == "__main__":
    main()