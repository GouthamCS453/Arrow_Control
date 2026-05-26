"""
Arrow Key Mouse Controller
==========================
Controls the mouse pointer using keyboard arrow keys.
Features a floating always-on-top toggle button.

Keybindings (when ENABLED):
  Arrow Keys     - Move mouse pointer (hold 2 for diagonal)
  A              - Left click
  D              - Right click
  W              - Scroll up
  S              - Scroll down
  E + Arrow Key  - Click & drag / select
  F2             - Toggle controller ON/OFF  (also the floating button)
  F4             - Exit the program entirely

When DISABLED the keyboard behaves 100% normally — F2 is the only key
still watched, everything else is untouched.

How suppression works
---------------------
ENABLED  → suppress=True listener: arrow/AWSD/E keys are consumed here
           and turned into mouse actions.  All other keys are re-emitted.
DISABLED → the suppress=True listener is stopped and replaced with a
           suppress=False listener that only watches F2.  The OS receives
           every keypress normally with zero interference.

Install dependencies:
  pip install pynput
  (tkinter ships with standard Python on Windows)
"""

import sys
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from pynput import mouse, keyboard
from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, KeyCode, Controller as KbController

# ── Configuration ─────────────────────────────────────────────────────────────

MOVE_STEP     = 5      # Base pixels per tick
ACCELERATION  = 2.5    # Speed multiplier when key held long enough
ACCEL_DELAY   = 0.4    # Seconds before acceleration kicks in
TICK_RATE     = 0.016  # ~60 ticks/sec
SCROLL_AMOUNT = 3      # Scroll lines per keypress

# ── Shared state ──────────────────────────────────────────────────────────────

mouse_ctrl = MouseController()
kb_ctrl    = KbController()

enabled  = True    # Current controller state
running  = True    # Set False to shut everything down

pressed   = set()   # Arrow/select keys currently held (only tracked when enabled)
key_times = {}
lock      = threading.Lock()

root: tk.Tk | None = None   # Tkinter root, set in main()

# Active listeners — we keep references so we can stop them on toggle
_active_listener: keyboard.Listener | None = None
_listener_lock = threading.Lock()

# ── Key definitions ───────────────────────────────────────────────────────────

MOVE_KEYS = {
    Key.up:    ( 0, -1),
    Key.down:  ( 0,  1),
    Key.left:  (-1,  0),
    Key.right: ( 1,  0),
}

SELECT_KEY  = KeyCode.from_char('e')
LCLICK_KEY  = KeyCode.from_char('a')
RCLICK_KEY  = KeyCode.from_char('d')
SCROLL_UP   = KeyCode.from_char('w')
SCROLL_DOWN = KeyCode.from_char('s')
TOGGLE_KEY  = Key.f2
QUIT_KEY    = Key.f4    # Hard exit — works in both enabled and disabled states

# Keys consumed by the controller when enabled
OWNED_KEYS = set(MOVE_KEYS.keys()) | {
    SELECT_KEY, LCLICK_KEY, RCLICK_KEY, SCROLL_UP, SCROLL_DOWN
}

# ── Movement helpers ──────────────────────────────────────────────────────────

def get_step(key) -> float:
    held = time.monotonic() - key_times.get(key, time.monotonic())
    return MOVE_STEP * ACCELERATION if held >= ACCEL_DELAY else MOVE_STEP

def active_move_keys():
    return [k for k in MOVE_KEYS if k in pressed]

def re_emit_press(key):
    try: kb_ctrl.press(key)
    except Exception: pass

def re_emit_release(key):
    try: kb_ctrl.release(key)
    except Exception: pass

# ── Arrow key matching (robust) ───────────────────────────────────────────────
# pynput can report arrow keys with varying vk codes on some platforms.
# We match by Key enum identity AND by vk as a fallback.

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

# ── Listener management ───────────────────────────────────────────────────────

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
    """suppress=True listener — intercepts controller keys, re-emits the rest."""
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
    """suppress=False listener — only watches F2/ESC, keyboard is fully normal."""
    global _active_listener
    _stop_active_listener()

    lst = keyboard.Listener(
        on_press=_on_press_disabled,
        on_release=None,
        suppress=False,          # ← OS sees every key normally
    )
    with _listener_lock:
        _active_listener = lst
    lst.start()

# ── Toggle ────────────────────────────────────────────────────────────────────

def do_toggle():
    global enabled
    enabled = not enabled
    label = "ENABLED ✓" if enabled else "DISABLED ✗"
    print(f"[Arrow Mouse] {label}")

    # Clear any held state so movement stops cleanly
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

# ── ENABLED listener callbacks (suppress=True) ────────────────────────────────

def _on_press_enabled(key):
    key = _canonical(key)

    if key == QUIT_KEY:
        do_exit()
        return False   # stops this listener

    if key == TOGGLE_KEY:
        threading.Thread(target=do_toggle, daemon=True).start()
        return         # consumed

    # Non-owned keys — pass through to OS
    if key not in OWNED_KEYS:
        re_emit_press(key)
        return

    # Register held key (idempotent — ignore if already held)
    with lock:
        if key not in pressed:
            pressed.add(key)
            key_times[key] = time.monotonic()

    # Instant single-fire actions — skip if SELECT is held (drag mode)
    with lock:
        select_held = SELECT_KEY in pressed

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

    if key == SCROLL_UP:
        mouse_ctrl.scroll(0,  SCROLL_AMOUNT); print("[Scroll] Up");   return
    if key == SCROLL_DOWN:
        mouse_ctrl.scroll(0, -SCROLL_AMOUNT); print("[Scroll] Down"); return
    # Arrow keys + SELECT_KEY → handled by move_loop


def _on_release_enabled(key):
    key = _canonical(key)

    if key not in OWNED_KEYS:
        re_emit_release(key)
        return

    with lock:
        was_in_pressed = key in pressed
        pressed.discard(key)
        key_times.pop(key, None)

    # Only release mouse button on SELECT release if drag was actually active
    # (move_loop manages drag_active; we signal via select leaving pressed set)
    # move_loop will detect SELECT_KEY gone from pressed and release the button.

# ── DISABLED listener callbacks (suppress=False) ──────────────────────────────

def _on_press_disabled(key):
    """Only intercept F2 and F4; everything else ignored (OS handles it)."""
    if key == QUIT_KEY:
        do_exit()
        return False

    if key == TOGGLE_KEY:
        threading.Thread(target=do_toggle, daemon=True).start()

# ── Movement loop ─────────────────────────────────────────────────────────────

def move_loop():
    drag_active = False
    while running:
        time.sleep(TICK_RATE)

        if not enabled:
            if drag_active:
                try: mouse_ctrl.release(Button.left)
                except Exception: pass
                drag_active = False
            continue

        with lock:
            dirs        = active_move_keys()
            select_held = SELECT_KEY in pressed

        # ── No arrow keys held ────────────────────────────────────────────────
        if not dirs:
            if drag_active:
                try: mouse_ctrl.release(Button.left)
                except Exception: pass
                drag_active = False
                print("[Select] Drag ended")
            continue

        # ── Arrow keys held — manage drag ─────────────────────────────────────
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

        # ── Compute movement ──────────────────────────────────────────────────
        dx = dy = 0.0
        for k in dirs:
            vx, vy = MOVE_KEYS[k]
            s = get_step(k)
            dx += vx * s
            dy += vy * s

        if dx != 0 and dy != 0:   # normalise diagonal speed
            dx *= 0.7071
            dy *= 0.7071

        try:
            mouse_ctrl.move(int(dx), int(dy))
        except Exception:
            pass

# ── Floating toggle window ────────────────────────────────────────────────────

ON_BG  = "#1DB954"
OFF_BG = "#3A3A4A"
ON_FG  = "#FFFFFF"
OFF_FG = "#AAAACC"
BTN_W  = 160
BTN_H  = 48

_drag_x = _drag_y = 0
_dragged = False


def build_toggle_window():
    global root

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.92)

    sw = root.winfo_screenwidth()
    root.geometry(f"{BTN_W}x{BTN_H}+{sw - BTN_W - 20}+20")

    root.canvas = tk.Canvas(root, width=BTN_W, height=BTN_H,
                            highlightthickness=0, bd=0)
    root.canvas.pack(fill="both", expand=True)

    _draw_pill()

    root.canvas.bind("<ButtonPress-1>",   _on_drag_start)
    root.canvas.bind("<B1-Motion>",       _on_drag_move)
    root.canvas.bind("<ButtonRelease-1>", _on_click_or_release)
    root.canvas.bind("<ButtonPress-3>",   lambda e: do_exit())

    root.mainloop()


def _draw_pill():
    c   = root.canvas
    bg  = ON_BG  if enabled else OFF_BG
    fg  = ON_FG  if enabled else OFF_FG
    txt = "Mouse Keys  ON" if enabled else "Mouse Keys  OFF"

    root.configure(bg=bg)
    c.configure(bg=bg)
    c.delete("all")

    r = BTN_H // 2
    c.create_arc(0, 0, r*2, BTN_H, start=90, extent=180, fill=bg, outline=bg)
    c.create_arc(BTN_W - r*2, 0, BTN_W, BTN_H, start=270, extent=180, fill=bg, outline=bg)
    c.create_rectangle(r, 0, BTN_W - r, BTN_H, fill=bg, outline=bg)

    # Highlight line
    hl = "#3de87a" if enabled else "#5a5a72"
    c.create_line(r, 3, BTN_W - r, 3, fill=hl, width=1)

    # Status dot
    dot = "#AAFFBB" if enabled else "#888899"
    c.create_oval(14, BTN_H//2 - 5, 24, BTN_H//2 + 5, fill=dot, outline="")

    try:
        fnt = tkfont.Font(family="Segoe UI", size=10, weight="bold")
    except Exception:
        fnt = ("TkDefaultFont", 10, "bold")

    c.create_text(BTN_W // 2 + 8, BTN_H // 2 - 4,
                  text=txt, fill=fg, font=fnt, anchor="center")

    try:
        hint_fnt = tkfont.Font(family="Segoe UI", size=7)
    except Exception:
        hint_fnt = ("TkDefaultFont", 7)

    hint_fg = "#88aa88" if enabled else "#666688"
    c.create_text(BTN_W // 2 + 8, BTN_H - 8,
                  text="F2 toggle · F4 / right-click exit",
                  fill=hint_fg, font=hint_fnt, anchor="center")


def refresh_button():
    if root:
        _draw_pill()


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

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    print("=" * 52)
    print("  Arrow Key Mouse Controller")
    print("=" * 52)
    print("  ↑ ↓ ← →    Move pointer")
    print("  A           Left click")
    print("  D           Right click")
    print("  W           Scroll up")
    print("  S           Scroll down")
    print("  E + Arrow   Click-drag / select")
    print("  F2          Toggle  (or click the floating button)")
    print("  F4          Exit program entirely")
    print("=" * 52)
    print("  Floating button: drag to move · right-click to exit")
    print("=" * 52)

    threading.Thread(target=move_loop, daemon=True).start()

    # Start with the suppressing listener (controller is ON by default)
    _start_enabled_listener()

    # Tkinter must run on the main thread
    build_toggle_window()

    print("\n[Arrow Mouse] Exited. Goodbye!")


if __name__ == "__main__":
    main()