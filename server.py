"""MCP server for a WLED 16×16 LED matrix."""
from __future__ import annotations

import asyncio
import base64
import json
import os
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from matrix import Matrix, _parse_color, push, scroll_text
from wled import WLEDClient

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
WLED_HOST = os.environ.get("WLED_HOST", "wled.local")
WLED_PORT = int(os.environ.get("WLED_PORT", "80"))
MATRIX_WIDTH = int(os.environ.get("MATRIX_WIDTH", "16"))
MATRIX_HEIGHT = int(os.environ.get("MATRIX_HEIGHT", "16"))
SERPENTINE = os.environ.get("MATRIX_SERPENTINE", "false").lower() not in ("false", "0", "no")
DEFAULT_BRIGHTNESS = int(os.environ.get("DEFAULT_BRIGHTNESS", "128"))

# ---------------------------------------------------------------------------
# Shared state (one client + matrix instance)
# ---------------------------------------------------------------------------
_client: WLEDClient | None = None
_matrix: Matrix | None = None


def get_client() -> WLEDClient:
    global _client
    if _client is None:
        _client = WLEDClient(WLED_HOST, WLED_PORT)
    return _client


def get_matrix() -> Matrix:
    global _matrix
    if _matrix is None:
        _matrix = Matrix(MATRIX_WIDTH, MATRIX_HEIGHT, SERPENTINE)
    return _matrix


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
app = Server("wled-matrix")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="wled_info",
            description="Get WLED device info: firmware version, LED count, signal strength, etc.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="wled_state",
            description="Get the current WLED state: power, brightness, effect, palette, colours.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="wled_power",
            description="Turn the matrix on or off.",
            inputSchema={
                "type": "object",
                "properties": {
                    "on": {"type": "boolean", "description": "true = on, false = off"}
                },
                "required": ["on"],
            },
        ),
        types.Tool(
            name="wled_brightness",
            description="Set the display brightness (0–255).",
            inputSchema={
                "type": "object",
                "properties": {
                    "brightness": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 255,
                        "description": "0 = off, 255 = maximum",
                    }
                },
                "required": ["brightness"],
            },
        ),
        types.Tool(
            name="wled_fill",
            description="Fill the entire matrix with a solid colour.",
            inputSchema={
                "type": "object",
                "properties": {
                    "color": {
                        "type": "string",
                        "description": "Hex colour string: 'FF0000' or '#FF0000'",
                    },
                    "brightness": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 255,
                        "description": "Optional brightness override",
                    },
                },
                "required": ["color"],
            },
        ),
        types.Tool(
            name="wled_clear",
            description="Turn off all LEDs (black frame).",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="wled_display_text",
            description=(
                "Display text on the 16×16 matrix using the built-in 5×7 pixel font. "
                "Text is centred vertically. Supports static display or animated scroll. "
                "For long strings, scrolling is recommended."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to display"},
                    "color": {
                        "type": "string",
                        "description": "Text colour hex (default: FFFFFF)",
                        "default": "FFFFFF",
                    },
                    "bg_color": {
                        "type": "string",
                        "description": "Background colour hex (default: 000000)",
                        "default": "000000",
                    },
                    "scroll": {
                        "type": "boolean",
                        "description": "Animate the text scrolling from right to left",
                        "default": False,
                    },
                    "scroll_speed_ms": {
                        "type": "integer",
                        "description": "Milliseconds per scroll step (default: 60)",
                        "default": 60,
                    },
                    "scroll_loops": {
                        "type": "integer",
                        "description": "How many times to scroll (default: 1)",
                        "default": 1,
                    },
                    "brightness": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 255,
                    },
                },
                "required": ["text"],
            },
        ),
        types.Tool(
            name="wled_display_image",
            description=(
                "Display an image on the 16×16 matrix. "
                "Accepts a URL, a local file path, or base64-encoded image data."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "HTTP/HTTPS URL of an image",
                    },
                    "path": {
                        "type": "string",
                        "description": "Absolute path to a local image file",
                    },
                    "base64": {
                        "type": "string",
                        "description": "Base64-encoded image bytes",
                    },
                    "brightness": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 255,
                    },
                },
            },
        ),
        types.Tool(
            name="wled_effect",
            description=(
                "Play one of WLED's built-in animated effects. "
                "Use wled_list_effects to see available effects."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "effect": {
                        "type": "string",
                        "description": "Effect name (case-insensitive) or numeric ID",
                    },
                    "palette": {
                        "type": "string",
                        "description": "Colour palette name or numeric ID (default: 0)",
                        "default": "0",
                    },
                    "speed": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 255,
                        "default": 128,
                    },
                    "intensity": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 255,
                        "default": 128,
                    },
                    "color": {
                        "type": "string",
                        "description": "Primary colour hex",
                        "default": "FFFFFF",
                    },
                    "brightness": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 255,
                    },
                },
                "required": ["effect"],
            },
        ),
        types.Tool(
            name="wled_list_effects",
            description="List all available WLED built-in effect names and their IDs.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="wled_list_palettes",
            description="List all available WLED colour palette names and their IDs.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="wled_draw_pixels",
            description=(
                "Send a raw pixel array to the matrix. "
                "Provide exactly width×height pixels as a flat list of [R,G,B] values."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pixels": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "minItems": 3,
                            "maxItems": 3,
                        },
                        "description": "Flat list of [R,G,B] tuples, length = width × height",
                    },
                    "brightness": {"type": "integer", "minimum": 0, "maximum": 255},
                },
                "required": ["pixels"],
            },
        ),
        types.Tool(
            name="wled_draw_shape",
            description="Draw a primitive shape: rectangle, line, or circle.",
            inputSchema={
                "type": "object",
                "properties": {
                    "shape": {
                        "type": "string",
                        "enum": ["rect", "line", "circle"],
                    },
                    "color": {"type": "string", "description": "Hex colour"},
                    "filled": {
                        "type": "boolean",
                        "description": "Fill the shape (rect/circle only)",
                        "default": False,
                    },
                    "x": {"type": "integer", "description": "Start X (rect/circle centre X / line x0)"},
                    "y": {"type": "integer", "description": "Start Y (rect/circle centre Y / line y0)"},
                    "x2": {"type": "integer", "description": "End X (line only)"},
                    "y2": {"type": "integer", "description": "End Y (line only)"},
                    "width": {"type": "integer", "description": "Width (rect only)"},
                    "height": {"type": "integer", "description": "Height (rect only)"},
                    "radius": {"type": "integer", "description": "Radius (circle only)"},
                    "clear_first": {
                        "type": "boolean",
                        "description": "Clear the canvas before drawing",
                        "default": True,
                    },
                    "brightness": {"type": "integer", "minimum": 0, "maximum": 255},
                },
                "required": ["shape", "color"],
            },
        ),
        types.Tool(
            name="wled_gradient",
            description="Fill the matrix with a linear gradient between two colours.",
            inputSchema={
                "type": "object",
                "properties": {
                    "color_start": {"type": "string", "description": "Start colour hex"},
                    "color_end": {"type": "string", "description": "End colour hex"},
                    "direction": {
                        "type": "string",
                        "enum": ["horizontal", "vertical"],
                        "default": "horizontal",
                    },
                    "brightness": {"type": "integer", "minimum": 0, "maximum": 255},
                },
                "required": ["color_start", "color_end"],
            },
        ),
        types.Tool(
            name="wled_pattern",
            description=(
                "Draw a built-in decorative pattern: "
                "'checkerboard', 'rainbow', or 'progress_bar'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "enum": ["checkerboard", "rainbow", "progress_bar"],
                    },
                    "color_a": {
                        "type": "string",
                        "description": "Primary colour hex (checkerboard / progress bar fill)",
                    },
                    "color_b": {
                        "type": "string",
                        "description": "Secondary colour hex (checkerboard alternate / progress bar bg)",
                    },
                    "value": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Fill fraction 0.0–1.0 (progress_bar only)",
                    },
                    "size": {
                        "type": "integer",
                        "description": "Square size in pixels (checkerboard only, default: 2)",
                        "default": 2,
                    },
                    "brightness": {"type": "integer", "minimum": 0, "maximum": 255},
                },
                "required": ["pattern"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------


def _ok(msg: str, extra: dict[str, Any] | None = None) -> list[types.TextContent]:
    payload = {"status": "ok", "message": msg}
    if extra:
        payload.update(extra)
    return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]


def _err(msg: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps({"status": "error", "message": msg}, indent=2))]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    client = get_client()
    matrix = get_matrix()

    try:
        # ---- info / state ------------------------------------------------
        if name == "wled_info":
            info = await client.get_info()
            return [types.TextContent(type="text", text=json.dumps(info, indent=2))]

        if name == "wled_state":
            state = await client.get_state()
            return [types.TextContent(type="text", text=json.dumps(state, indent=2))]

        # ---- power / brightness ------------------------------------------
        if name == "wled_power":
            await client.set_power(arguments["on"])
            return _ok(f"Power {'on' if arguments['on'] else 'off'}")

        if name == "wled_brightness":
            await client.set_brightness(arguments["brightness"])
            return _ok(f"Brightness set to {arguments['brightness']}")

        # ---- fill / clear ------------------------------------------------
        if name == "wled_fill":
            color = _parse_color(arguments["color"])
            bri = arguments.get("brightness", DEFAULT_BRIGHTNESS)
            matrix.fill(color)
            await push(matrix, client, bri)
            return _ok(f"Filled with #{arguments['color']}")

        if name == "wled_clear":
            matrix.clear()
            await push(matrix, client)
            return _ok("Matrix cleared")

        # ---- text --------------------------------------------------------
        if name == "wled_display_text":
            text = arguments["text"]
            color = _parse_color(arguments.get("color", "FFFFFF"))
            bg = _parse_color(arguments.get("bg_color", "000000"))
            bri = arguments.get("brightness", DEFAULT_BRIGHTNESS)
            do_scroll = arguments.get("scroll", False)
            speed = arguments.get("scroll_speed_ms", 60)
            loops = arguments.get("scroll_loops", 1)

            if do_scroll:
                for _ in range(loops):
                    await scroll_text(matrix, client, text, color, bg, speed, bri)
                return _ok(f"Scrolled '{text}' × {loops}")
            else:
                matrix.render_text_frame(text, 0, color, bg)
                await push(matrix, client, bri)
                fits = matrix.text_width(text) <= matrix.width
                return _ok(
                    f"Displayed '{text}'" + ("" if fits else " (truncated — consider scroll=true)"),
                    {"text_px_width": matrix.text_width(text)},
                )

        # ---- image -------------------------------------------------------
        if name == "wled_display_image":
            bri = arguments.get("brightness", DEFAULT_BRIGHTNESS)
            if "url" in arguments:
                await matrix.load_image_url(arguments["url"])
                source = arguments["url"]
            elif "path" in arguments:
                matrix.load_image_path(arguments["path"])
                source = arguments["path"]
            elif "base64" in arguments:
                matrix.load_image_bytes(base64.b64decode(arguments["base64"]))
                source = "<base64>"
            else:
                return _err("Provide one of: url, path, base64")
            await push(matrix, client, bri)
            return _ok(f"Image loaded from {source}")

        # ---- WLED effects ------------------------------------------------
        if name == "wled_effect":
            effects = await client.get_effects()
            eff_arg = arguments["effect"]
            try:
                effect_id = int(eff_arg)
            except ValueError:
                matches = [
                    i for i, e in enumerate(effects)
                    if eff_arg.lower() in e.lower()
                ]
                if not matches:
                    return _err(
                        f"Effect '{eff_arg}' not found. "
                        f"Use wled_list_effects to see all options."
                    )
                effect_id = matches[0]

            palettes = await client.get_palettes()
            pal_arg = arguments.get("palette", "0")
            try:
                palette_id = int(pal_arg)
            except ValueError:
                pal_matches = [
                    i for i, p in enumerate(palettes)
                    if pal_arg.lower() in p.lower()
                ]
                palette_id = pal_matches[0] if pal_matches else 0

            color = _parse_color(arguments.get("color", "FFFFFF"))
            bri = arguments.get("brightness", DEFAULT_BRIGHTNESS)
            await client.set_effect(
                effect_id=effect_id,
                palette_id=palette_id,
                speed=arguments.get("speed", 128),
                intensity=arguments.get("intensity", 128),
                color=color,
                brightness=bri,
            )
            eff_name = effects[effect_id] if effect_id < len(effects) else str(effect_id)
            return _ok(f"Effect '{eff_name}' (id={effect_id}) started")

        if name == "wled_list_effects":
            effects = await client.get_effects()
            items = [{"id": i, "name": e} for i, e in enumerate(effects)]
            return [types.TextContent(type="text", text=json.dumps(items, indent=2))]

        if name == "wled_list_palettes":
            palettes = await client.get_palettes()
            items = [{"id": i, "name": p} for i, p in enumerate(palettes)]
            return [types.TextContent(type="text", text=json.dumps(items, indent=2))]

        # ---- raw pixels --------------------------------------------------
        if name == "wled_draw_pixels":
            raw = arguments["pixels"]
            if len(raw) != matrix.width * matrix.height:
                return _err(
                    f"Expected {matrix.width * matrix.height} pixels, got {len(raw)}"
                )
            matrix.pixels = [(p[0], p[1], p[2]) for p in raw]
            bri = arguments.get("brightness", DEFAULT_BRIGHTNESS)
            await push(matrix, client, bri)
            return _ok(f"Pushed {len(raw)} raw pixels")

        # ---- shapes ------------------------------------------------------
        if name == "wled_draw_shape":
            shape = arguments["shape"]
            color = _parse_color(arguments["color"])
            if arguments.get("clear_first", True):
                matrix.clear()

            if shape == "rect":
                matrix.draw_rect(
                    arguments.get("x", 0),
                    arguments.get("y", 0),
                    arguments.get("width", matrix.width),
                    arguments.get("height", matrix.height),
                    color,
                    filled=arguments.get("filled", False),
                )
            elif shape == "line":
                matrix.draw_line(
                    arguments.get("x", 0), arguments.get("y", 0),
                    arguments.get("x2", matrix.width - 1),
                    arguments.get("y2", matrix.height - 1),
                    color,
                )
            elif shape == "circle":
                matrix.draw_circle(
                    arguments.get("x", matrix.width // 2),
                    arguments.get("y", matrix.height // 2),
                    arguments.get("radius", 6),
                    color,
                    filled=arguments.get("filled", False),
                )

            bri = arguments.get("brightness", DEFAULT_BRIGHTNESS)
            await push(matrix, client, bri)
            return _ok(f"Drew {shape}")

        # ---- gradient ----------------------------------------------------
        if name == "wled_gradient":
            c_start = _parse_color(arguments["color_start"])
            c_end = _parse_color(arguments["color_end"])
            direction = arguments.get("direction", "horizontal")
            matrix.draw_gradient(c_start, c_end, direction)
            bri = arguments.get("brightness", DEFAULT_BRIGHTNESS)
            await push(matrix, client, bri)
            return _ok(f"Gradient applied ({direction})")

        # ---- patterns ----------------------------------------------------
        if name == "wled_pattern":
            pattern = arguments["pattern"]
            bri = arguments.get("brightness", DEFAULT_BRIGHTNESS)

            if pattern == "checkerboard":
                ca = _parse_color(arguments.get("color_a", "FFFFFF"))
                cb = _parse_color(arguments.get("color_b", "000000"))
                size = arguments.get("size", 2)
                matrix.checkerboard(ca, cb, size)

            elif pattern == "rainbow":
                matrix.rainbow()

            elif pattern == "progress_bar":
                value = float(arguments.get("value", 0.5))
                ca = _parse_color(arguments.get("color_a", "00C800"))
                cb = _parse_color(arguments.get("color_b", "141414"))
                matrix.progress_bar(value, ca, cb)

            await push(matrix, client, bri)
            return _ok(f"Pattern '{pattern}' drawn")

        return _err(f"Unknown tool: {name}")

    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ---------------------------------------------------------------------------
# Resources: expose device info + effect list
# ---------------------------------------------------------------------------


@app.list_resources()
async def list_resources() -> list[types.Resource]:
    return [
        types.Resource(
            uri="wled://effects",
            name="WLED Effects",
            description="Full list of built-in WLED animated effects",
            mimeType="application/json",
        ),
        types.Resource(
            uri="wled://palettes",
            name="WLED Palettes",
            description="Full list of built-in WLED colour palettes",
            mimeType="application/json",
        ),
        types.Resource(
            uri="wled://info",
            name="Device Info",
            description="WLED firmware and hardware information",
            mimeType="application/json",
        ),
    ]


@app.read_resource()
async def read_resource(uri: str) -> str:  # type: ignore[return]
    client = get_client()
    if uri == "wled://effects":
        effects = await client.get_effects()
        return json.dumps([{"id": i, "name": e} for i, e in enumerate(effects)], indent=2)
    if uri == "wled://palettes":
        palettes = await client.get_palettes()
        return json.dumps([{"id": i, "name": p} for i, p in enumerate(palettes)], indent=2)
    if uri == "wled://info":
        return json.dumps(await client.get_info(), indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _serve() -> None:
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
