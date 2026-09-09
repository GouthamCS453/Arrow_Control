# Arrow Key Mouse Controller

A Python utility that allows you to control your mouse pointer and perform mouse actions using keyboard arrow keys. Features a floating always-on-top toggle button for easy state management.

## Features

✓ **Arrow key mouse control** — Move the mouse pointer in all directions  
✓ **Click and drag/select** — Use keyboard combos for complex interactions  
✓ **Scroll support** — Scroll up and down with dedicated keys  
✓ **Double-click & Middle-click** — Dedicated single-key actions (Z, Q)  
✓ **Smooth speed ramp** — Cursor accelerates gradually like an analog stick  
✓ **Precision & Turbo modes** — Shift (slow) and Ctrl (fast) speed modifiers  
✓ **Momentary mouse mode** — Hold Caps Lock for temporary mouse control while typing  
✓ **Editable speed settings** — GUI settings window, changes apply instantly  
✓ **Floating hover cheat-sheet** — Hover the widget to see all key bindings  
✓ **Floating toggle button** — Visual indicator and quick toggle  
✓ **Zero interference when disabled** — When OFF, your keyboard behaves 100% normally  
✓ **Easy hotkeys** — F2 to toggle, F4 to exit  

## Installation

### Requirements
- Python 3.7+
- `pynput` library
- `tkinter` (comes with standard Python on Windows)

### Setup

1. Clone or download this repository
2. Install the required dependency:
   ```bash
   pip install pynput
   ```

## Usage

Run the program:
```bash
python mouse_key.py
```

A floating green/gray toggle button will appear in the top-right corner of your screen.

### Keybindings (When Enabled ✓)

| Key(s) | Action |
|--------|--------|
| `↑ ↓ ← →` | Move mouse pointer |
| `A` | Left click |
| `Z` | Double left click |
| `D` | Right click |
| `Q` | Middle click |
| `W` | Scroll up |
| `S` | Scroll down |
| `E + Arrow Key` | Click & drag / select |
| `Shift + Arrow` | Precision / slow movement |
| `Ctrl + Arrow` | Turbo / fast movement |
| `Caps Lock` (hold) | Momentary mouse mode (while controller is OFF) |
| `F2` | Toggle controller ON/OFF |
| `F4` | Exit program entirely |

**When Disabled ✗:** All keys pass through normally to the OS. Only F2, F4, and Caps Lock (momentary) are monitored.

### Mouse Interactions

- **Hover the floating button** — Expand to show full key guide
- **Click the floating button** — Toggle ON/OFF
- **Drag the floating button** — Move it around the screen
- **Right-click the floating button** — Open speed settings window

### Momentary Mode (Caps Lock)

When the controller is **latched OFF** (toggled off via F2), you can temporarily activate mouse mode by **holding Caps Lock**. The moment you release Caps Lock, the keyboard returns to normal typing.

This is ideal for quick one-off clicks during typing — no need to toggle F2 back and forth.

## Configuration

Speed settings can be changed in two ways:

### 1. Settings Window (Recommended)
Right-click the floating widget to open the settings window. Edit values and click **Save** — changes take effect immediately without restarting.

### 2. Edit `config.json` directly
`config.json` is auto-created next to `mouse_key.py` on first run:

```json
{
    "min_speed": 3,
    "max_speed": 16,
    "ramp_time": 0.5
}
```

| Setting | Description |
|---------|-------------|
| `min_speed` | Starting speed in pixels per tick (first tap response) |
| `max_speed` | Top speed in pixels per tick (after holding the key) |
| `ramp_time` | Seconds to ramp smoothly from min to max speed |

> Fixed constants (TICK_RATE, SCROLL_AMOUNT) can still be edited at the top of `mouse_key.py`.

## How It Works

### State Management
- **ENABLED** → Arrow/AWSD/E/Z/Q keys are intercepted and converted to mouse actions. All other keys are re-emitted to the OS.
- **DISABLED** → A minimal listener only watches F2, F4, and Caps Lock. Every other keystroke reaches the OS untouched.
- **MOMENTARY** → Triggered by holding Caps Lock while disabled. Temporarily activates mouse mode without changing the latch state.

### Movement — Smooth Ramp
Speed increases linearly from `min_speed` to `max_speed` over `ramp_time` seconds:

```
speed = min_speed + (max_speed - min_speed) × min(1.0, held_time / ramp_time)
```

No sudden speed jump — the cursor feels like an analog joystick.

**Speed modifiers applied on top:**
- `Shift` → 0.3× (precision)
- `Ctrl` → 2.5× (turbo)
- Diagonal movements are normalised to prevent speed boost.

### Drag/Select Mode
- When `E` is held and arrow keys are pressed, the left mouse button stays pressed
- Useful for text selection, dragging elements, or drawing operations
- Button releases automatically when `E` is released

## Troubleshooting

**Keys not responding?**
- Ensure the program window has focus (or is running in the background)
- Check that the controller is ENABLED (green floating widget)
- Try restarting the program

**Floating button stuck?**
- Press F4 to exit
- Click and drag to reposition

**High CPU usage?**
- The movement loop runs at ~60 Hz (every 16ms). This is intentional for smooth control.
- Adjust `TICK_RATE` in the source if needed, but values below 0.016 may cause jitter.

---

## Known Bugs

These issues are documented for tracking and will be addressed in a future update.

---

### BUG-01 — Game Bar Overlay Conflict (Open/Close Loop)

**Condition:** Occurs when the controller is **enabled** (toggle ON) and the Windows Game Bar shortcut (`Win + G`) is invoked.

**Symptom:** Because the controller suppresses and re-emits keys, the Game Bar overlay intercepts the re-emitted input and enters a rapid open/close loop, competing with the controller's key suppression. This can cause the UI to flicker or become unresponsive until the controller is toggled OFF.

**Workaround:** Toggle the controller OFF (`F2`) before opening the Game Bar, or disable the Game Bar shortcut in Windows Settings → Gaming → Game Bar.

---

### BUG-02 — Momentary Mouse Mode (Scroll Lock) Not Working

**Condition:** Holding `Scroll Lock` while the controller is latched OFF does not reliably activate temporary mouse mode.

**Symptom:** The `_on_press_disabled` and `_on_release_disabled` callbacks do not consistently fire for `Scroll Lock` on all Windows configurations, so the momentary enable/disable cycle either does not trigger or does not cleanly release.

**Workaround:** Use the `F2` latch toggle instead until this is fixed.

---

### BUG-03 — Base Movement Speed and Acceleration Partially Hardcoded

**Condition:** The `Shift` precision multiplier (`0.3×`) and the `Ctrl` turbo multiplier (`2.5×`) are hardcoded in `get_step()` in `mouse_key.py` and are not exposed in `config.json` or the Settings window.

**Symptom:** Users who want to customise precision or turbo sensitivity must edit the source code directly. The Settings window only exposes `min_speed`, `max_speed`, and `ramp_time`.

**Workaround:** Open `mouse_key.py` and locate `get_step()` in Section 5. Edit the `0.3` (precision) and `2.5` (turbo) multiplier values manually.

---

### BUG-04 — Conflicts with OS-Level Shortcuts and Elevated Windows

**Condition:** Any OS-level keybind or application shortcut that has higher input priority than a user-mode process (e.g., `Win + *` shortcuts, UAC prompts, Task Manager, Remote Desktop) may receive re-emitted keys unintentionally when the controller is enabled.

**Symptom:** Pressing an unowned key while the controller is ON causes it to be re-emitted via `pynput`, which can accidentally trigger OS shortcuts that share the same keycode. Additionally, the controller cannot send input to elevated (admin-level) windows unless it is itself run as administrator.

**Workaround:** Run `mouse_key.py` as administrator to resolve issues with elevated windows. For OS shortcut conflicts, toggle the controller OFF before using affected key combinations.

---

## License

Free to use and modify for personal use.

## Notes

- This program uses keyboard suppression. When enabled, the monitored keys are consumed and do not reach other applications.
- Run with administrator privileges if you experience issues controlling windows with elevated permissions.
- The floating button is always on top and stays visible across all workspaces on Windows.
- The momentary mouse key is currently assigned to `Scroll Lock`. This can be changed by editing `MOMENTARY_KEY` in Section 3 of `mouse_key.py`.
- There may be more bugs within the program yet to be found ,Further testing is being done.
