# Arrow Key Mouse Controller

A Python utility that allows you to control your mouse pointer and perform mouse actions using keyboard arrow keys. Features a floating always-on-top toggle button for easy state management.

## Features

✓ **Arrow key mouse control** — Move the mouse pointer in all directions  
✓ **Click and drag/select** — Use keyboard combos for complex interactions  
✓ **Scroll support** — Scroll up and down with dedicated keys  
✓ **Floating toggle button** — Visual indicator and quick toggle without leaving keyboard  
✓ **Smooth movement** — Acceleration kicks in after holding keys, normalized diagonal speed  
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
| `D` | Right click |
| `W` | Scroll up |
| `S` | Scroll down |
| `E + Arrow Key` | Click & drag / select |
| `F2` | Toggle controller ON/OFF |
| `F4` | Exit program entirely |

**When Disabled ✗:** All keys pass through normally to the OS. Only F2 and F4 are still monitored.

### Mouse Interactions

- **Click the floating button** — Toggle ON/OFF
- **Drag the floating button** — Move it around the screen
- **Right-click the floating button** — Exit the program

## Configuration

Edit these constants at the top of `mouse_key.py` to customize behavior:

```python
MOVE_STEP     = 5      # Base pixels per tick
ACCELERATION  = 2.5    # Speed multiplier when key held long enough
ACCEL_DELAY   = 0.4    # Seconds before acceleration kicks in
TICK_RATE     = 0.016  # ~60 ticks/sec
SCROLL_AMOUNT = 3      # Scroll lines per keypress
```

## How It Works

### State Management
- **ENABLED** → Arrow/WASD/E keys are intercepted and converted to mouse actions. All other keys are re-emitted to the OS.
- **DISABLED** → A minimal listener only watches F2 and F4. Every other keystroke reaches the OS untouched.

### Movement
- Base movement speed increases with **acceleration** after being held for `ACCEL_DELAY` seconds
- Diagonal movements are normalized to prevent diagonal speed boost
- Movement updates happen at ~60 ticks per second for smooth, responsive control

### Drag/Select Mode
- When `E` is held and arrow keys are pressed, the left mouse button stays pressed
- Useful for text selection, dragging elements, or drawing operations
- Button releases automatically when `E` is released

## Troubleshooting

**Keys not responding?**
- Ensure the program window has focus (or is running in the background)
- Check that the controller is ENABLED (green button on floating widget)
- Try restarting the program

**Floating button stuck?**
- Right-click it or press F4 to exit
- Click and drag to reposition

**High CPU usage?**
- The movement loop runs at ~60 Hz (every 16ms). This is intentional for smooth control.
- Adjust `TICK_RATE` if needed, but values below 0.016 may cause jitter.

## License

Free to use and modify for personal use.

## Notes

- This program uses keyboard suppression. When enabled, the monitored keys are consumed and do not reach other applications.
- Run with administrator privileges if you experience issues controlling windows with elevated permissions.
- The floating button is always on top and stays visible across all workspaces on Windows.
