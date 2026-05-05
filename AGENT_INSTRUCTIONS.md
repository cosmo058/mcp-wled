# WLED Matrix MCP — Agent Instructions

You have access to a 16×16 RGB LED matrix running WLED firmware via the `wled_*` MCP tools.
The display is **256 LEDs** total, all rows run left→right (no serpentine).

---

## Setup & connection

The server communicates over **stdio** — the MCP client spawns it as a subprocess.

### Local (Python)
```bash
# Install
cd mcp-wled && uv pip install -e .

# Run (stdio — called by MCP client, not manually)
python server.py
```

### Docker
```bash
# Build
docker compose build

# The MCP client runs the container on demand:
docker run --rm -i --network host --env-file .env mcp-wled
```

### Claude Desktop / claude_desktop_config.json

**Local:**
```json
{
  "mcpServers": {
    "wled": {
      "command": "python",
      "args": ["/path/to/mcp-wled/server.py"],
      "env": {
        "WLED_HOST": "192.168.50.111",
        "MATRIX_SERPENTINE": "false",
        "DEFAULT_BRIGHTNESS": "128"
      }
    }
  }
}
```

**Docker:**
```json
{
  "mcpServers": {
    "wled": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "--network", "host",
               "--env-file", "/path/to/mcp-wled/.env",
               "mcp-wled"]
    }
  }
}
```

### Environment variables
| Variable | Default | Description |
|---|---|---|
| `WLED_HOST` | `wled.local` | WLED device IP or hostname |
| `WLED_PORT` | `80` | WLED HTTP port |
| `MATRIX_WIDTH` | `16` | Matrix width in pixels |
| `MATRIX_HEIGHT` | `16` | Matrix height in pixels |
| `MATRIX_SERPENTINE` | `false` | Serpentine wiring (false = all rows L→R) |
| `DEFAULT_BRIGHTNESS` | `128` | Default brightness 0–255 |

---

---

## Display constraints

| Property | Value |
|---|---|
| Size | 16 × 16 pixels |
| Total LEDs | 256 |
| Color format | Hex string: `"FF0000"` or `"#FF0000"` |
| Brightness range | 0–255 (default 128) |
| Font | Built-in 5×7 pixel bitmap font |

---

## Tool reference

### Status & control
- **`wled_info`** — device firmware, LED count, WiFi signal. Call this first to verify connectivity.
- **`wled_state`** — current power, brightness, active effect.
- **`wled_power`** — `{"on": true/false}` — turn the matrix on or off.
- **`wled_brightness`** — `{"brightness": 0–255}` — global brightness.

### Solid colour & clear
- **`wled_fill`** — `{"color": "FF6600"}` — fill all 256 LEDs with one colour.
- **`wled_clear`** — turn off all LEDs (black frame).

### Text
- **`wled_display_text`** — render text using the 5×7 pixel font.
  - Static: fits ~2–3 characters on screen at once.
  - For anything longer than 3 chars, always set `"scroll": true`.
  - `scroll_speed_ms`: 40–80 ms per step is comfortable (default 60).
  - `scroll_loops`: how many times to repeat the scroll (default 1).
  - `color` and `bg_color` are hex strings.

```json
{"text": "Hi!", "color": "FFCC00", "bg_color": "000000"}
{"text": "Hello World", "color": "00FFFF", "scroll": true, "scroll_speed_ms": 60}
```

### Images
- **`wled_display_image`** — resize any image to 16×16 and display it.
  - Provide exactly one of: `url`, `path`, or `base64`.
  - Images are auto-resized with LANCZOS filtering.

```json
{"url": "https://example.com/icon.png"}
{"path": "/home/user/photo.jpg"}
```

### Built-in effects
- **`wled_list_effects`** — returns all ~187 effect names with their IDs.
- **`wled_list_palettes`** — returns all ~71 palette names with their IDs.
- **`wled_effect`** — play an animated effect by name or ID.
  - `speed` and `intensity`: 0–255 (default 128).
  - `color`: primary colour for effects that use it.

```json
{"effect": "Rainbow", "speed": 150}
{"effect": "Fire 2012", "palette": "Flame", "intensity": 200}
{"effect": 0}
```

### Drawing primitives
- **`wled_draw_shape`** — draw a rect, line, or circle.
  - `clear_first: true` (default) clears the canvas before drawing.
  - Rect: needs `x, y, width, height`.
  - Line: needs `x, y, x2, y2`.
  - Circle: needs `x, y` (centre) and `radius`.

```json
{"shape": "rect", "color": "FF0000", "x": 2, "y": 2, "width": 12, "height": 12, "filled": true}
{"shape": "circle", "color": "00FF00", "x": 7, "y": 7, "radius": 6}
{"shape": "line", "color": "FFFFFF", "x": 0, "y": 0, "x2": 15, "y2": 15}
```

- **`wled_gradient`** — fill with a gradient between two colours.

```json
{"color_start": "FF0000", "color_end": "0000FF", "direction": "horizontal"}
```

- **`wled_pattern`** — named patterns:
  - `checkerboard`: `color_a`, `color_b`, `size` (px per square, default 2).
  - `rainbow`: full-spectrum horizontal sweep, no args needed.
  - `progress_bar`: `value` (0.0–1.0), `color_a` (fill), `color_b` (background).

```json
{"pattern": "progress_bar", "value": 0.75, "color_a": "00FF00"}
{"pattern": "checkerboard", "color_a": "FFFFFF", "color_b": "000000", "size": 2}
```

- **`wled_draw_pixels`** — send a raw 256-element `[[R,G,B], ...]` array.
  Use this for custom animations or programmatically generated frames.

---

## Recipes

**Show status / progress:**
```
wled_pattern {"pattern": "progress_bar", "value": 0.6, "color_a": "00CC00"}
```

**Notification flash:**
```
wled_fill {"color": "FF4400", "brightness": 200}
# wait
wled_clear {}
```

**Scrolling announcement:**
```
wled_display_text {"text": "Build passed!", "color": "00FF88", "scroll": true, "scroll_loops": 2}
```

**Ambient mood:**
```
wled_effect {"effect": "Colorloop", "speed": 80}
```

**Display an icon:**
```
wled_display_image {"url": "https://...16x16-icon.png"}
```

---

## Behaviour guidelines

- After displaying something static, leave it on unless instructed to clear.
- For long-running effects (`wled_effect`), they loop automatically — no need to call repeatedly.
- `wled_clear` + `wled_power off` fully silences the display.
- Brightness above 200 at close range is very bright — prefer 100–160 for indoor use.
- When in doubt about available effects, call `wled_list_effects` first.
