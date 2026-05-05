"""16x16 LED matrix abstraction and rendering utilities."""
from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING

import httpx
from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from wled import WLEDClient

Pixel = tuple[int, int, int]

# ---------------------------------------------------------------------------
# Embedded 5×7 bitmap font (printable ASCII 32–126)
# Each entry is 7 rows × 5 cols packed as 5-bit int, MSB = leftmost pixel.
# ---------------------------------------------------------------------------
_FONT_5X7: dict[str, list[int]] = {
    " ": [0b00000] * 7,
    "!": [0b00100, 0b00100, 0b00100, 0b00100, 0b00000, 0b00000, 0b00100],
    '"': [0b01010, 0b01010, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000],
    "#": [0b01010, 0b11111, 0b01010, 0b01010, 0b11111, 0b01010, 0b00000],
    "$": [0b00100, 0b01111, 0b10100, 0b01110, 0b00101, 0b11110, 0b00100],
    "%": [0b11000, 0b11001, 0b00010, 0b00100, 0b01000, 0b10011, 0b00011],
    "&": [0b01100, 0b10010, 0b10100, 0b01000, 0b10101, 0b10010, 0b01101],
    "'": [0b00100, 0b00100, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000],
    "(": [0b00010, 0b00100, 0b01000, 0b01000, 0b01000, 0b00100, 0b00010],
    ")": [0b01000, 0b00100, 0b00010, 0b00010, 0b00010, 0b00100, 0b01000],
    "*": [0b00000, 0b00100, 0b10101, 0b01110, 0b10101, 0b00100, 0b00000],
    "+": [0b00000, 0b00100, 0b00100, 0b11111, 0b00100, 0b00100, 0b00000],
    ",": [0b00000, 0b00000, 0b00000, 0b00000, 0b00110, 0b00100, 0b01000],
    "-": [0b00000, 0b00000, 0b00000, 0b11111, 0b00000, 0b00000, 0b00000],
    ".": [0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b01100, 0b01100],
    "/": [0b00001, 0b00010, 0b00100, 0b01000, 0b10000, 0b00000, 0b00000],
    "0": [0b01110, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b01110],
    "1": [0b00100, 0b01100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110],
    "2": [0b01110, 0b10001, 0b00001, 0b00110, 0b01000, 0b10000, 0b11111],
    "3": [0b11111, 0b00010, 0b00100, 0b00110, 0b00001, 0b10001, 0b01110],
    "4": [0b00010, 0b00110, 0b01010, 0b10010, 0b11111, 0b00010, 0b00010],
    "5": [0b11111, 0b10000, 0b11110, 0b00001, 0b00001, 0b10001, 0b01110],
    "6": [0b00110, 0b01000, 0b10000, 0b11110, 0b10001, 0b10001, 0b01110],
    "7": [0b11111, 0b00001, 0b00010, 0b00100, 0b01000, 0b01000, 0b01000],
    "8": [0b01110, 0b10001, 0b10001, 0b01110, 0b10001, 0b10001, 0b01110],
    "9": [0b01110, 0b10001, 0b10001, 0b01111, 0b00001, 0b00010, 0b01100],
    ":": [0b00000, 0b01100, 0b01100, 0b00000, 0b01100, 0b01100, 0b00000],
    ";": [0b00000, 0b01100, 0b01100, 0b00000, 0b01100, 0b00100, 0b01000],
    "<": [0b00010, 0b00100, 0b01000, 0b10000, 0b01000, 0b00100, 0b00010],
    "=": [0b00000, 0b00000, 0b11111, 0b00000, 0b11111, 0b00000, 0b00000],
    ">": [0b10000, 0b01000, 0b00100, 0b00010, 0b00100, 0b01000, 0b10000],
    "?": [0b01110, 0b10001, 0b00001, 0b00110, 0b00100, 0b00000, 0b00100],
    "@": [0b01110, 0b10001, 0b10111, 0b10101, 0b10110, 0b10000, 0b01111],
    "A": [0b01110, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001],
    "B": [0b11110, 0b10001, 0b10001, 0b11110, 0b10001, 0b10001, 0b11110],
    "C": [0b01110, 0b10001, 0b10000, 0b10000, 0b10000, 0b10001, 0b01110],
    "D": [0b11100, 0b10010, 0b10001, 0b10001, 0b10001, 0b10010, 0b11100],
    "E": [0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b11111],
    "F": [0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b10000],
    "G": [0b01110, 0b10001, 0b10000, 0b10111, 0b10001, 0b10001, 0b01111],
    "H": [0b10001, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001],
    "I": [0b01110, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110],
    "J": [0b00111, 0b00010, 0b00010, 0b00010, 0b00010, 0b10010, 0b01100],
    "K": [0b10001, 0b10010, 0b10100, 0b11000, 0b10100, 0b10010, 0b10001],
    "L": [0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b11111],
    "M": [0b10001, 0b11011, 0b10101, 0b10101, 0b10001, 0b10001, 0b10001],
    "N": [0b10001, 0b11001, 0b10101, 0b10101, 0b10011, 0b10001, 0b10001],
    "O": [0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110],
    "P": [0b11110, 0b10001, 0b10001, 0b11110, 0b10000, 0b10000, 0b10000],
    "Q": [0b01110, 0b10001, 0b10001, 0b10001, 0b10101, 0b10010, 0b01101],
    "R": [0b11110, 0b10001, 0b10001, 0b11110, 0b10100, 0b10010, 0b10001],
    "S": [0b01111, 0b10000, 0b10000, 0b01110, 0b00001, 0b00001, 0b11110],
    "T": [0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100],
    "U": [0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110],
    "V": [0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01010, 0b00100],
    "W": [0b10001, 0b10001, 0b10001, 0b10101, 0b10101, 0b11011, 0b10001],
    "X": [0b10001, 0b10001, 0b01010, 0b00100, 0b01010, 0b10001, 0b10001],
    "Y": [0b10001, 0b10001, 0b01010, 0b00100, 0b00100, 0b00100, 0b00100],
    "Z": [0b11111, 0b00001, 0b00010, 0b00100, 0b01000, 0b10000, 0b11111],
    "[": [0b01110, 0b01000, 0b01000, 0b01000, 0b01000, 0b01000, 0b01110],
    "\\": [0b10000, 0b01000, 0b00100, 0b00010, 0b00001, 0b00000, 0b00000],
    "]": [0b01110, 0b00010, 0b00010, 0b00010, 0b00010, 0b00010, 0b01110],
    "^": [0b00100, 0b01010, 0b10001, 0b00000, 0b00000, 0b00000, 0b00000],
    "_": [0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b11111],
    "`": [0b01000, 0b00100, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000],
    "a": [0b00000, 0b00000, 0b01110, 0b00001, 0b01111, 0b10001, 0b01111],
    "b": [0b10000, 0b10000, 0b11110, 0b10001, 0b10001, 0b10001, 0b11110],
    "c": [0b00000, 0b00000, 0b01110, 0b10000, 0b10000, 0b10001, 0b01110],
    "d": [0b00001, 0b00001, 0b01111, 0b10001, 0b10001, 0b10001, 0b01111],
    "e": [0b00000, 0b00000, 0b01110, 0b10001, 0b11111, 0b10000, 0b01110],
    "f": [0b00110, 0b01001, 0b01000, 0b11100, 0b01000, 0b01000, 0b01000],
    "g": [0b00000, 0b01111, 0b10001, 0b10001, 0b01111, 0b00001, 0b01110],
    "h": [0b10000, 0b10000, 0b11110, 0b10001, 0b10001, 0b10001, 0b10001],
    "i": [0b00100, 0b00000, 0b01100, 0b00100, 0b00100, 0b00100, 0b01110],
    "j": [0b00010, 0b00000, 0b00110, 0b00010, 0b00010, 0b10010, 0b01100],
    "k": [0b10000, 0b10000, 0b10010, 0b10100, 0b11000, 0b10100, 0b10010],
    "l": [0b01100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110],
    "m": [0b00000, 0b00000, 0b11010, 0b10101, 0b10101, 0b10001, 0b10001],
    "n": [0b00000, 0b00000, 0b11110, 0b10001, 0b10001, 0b10001, 0b10001],
    "o": [0b00000, 0b00000, 0b01110, 0b10001, 0b10001, 0b10001, 0b01110],
    "p": [0b00000, 0b11110, 0b10001, 0b10001, 0b11110, 0b10000, 0b10000],
    "q": [0b00000, 0b01111, 0b10001, 0b10001, 0b01111, 0b00001, 0b00001],
    "r": [0b00000, 0b00000, 0b10110, 0b11001, 0b10000, 0b10000, 0b10000],
    "s": [0b00000, 0b00000, 0b01110, 0b10000, 0b01110, 0b00001, 0b11110],
    "t": [0b01000, 0b01000, 0b11110, 0b01000, 0b01000, 0b01001, 0b00110],
    "u": [0b00000, 0b00000, 0b10001, 0b10001, 0b10001, 0b10011, 0b01101],
    "v": [0b00000, 0b00000, 0b10001, 0b10001, 0b10001, 0b01010, 0b00100],
    "w": [0b00000, 0b00000, 0b10001, 0b10101, 0b10101, 0b10101, 0b01010],
    "x": [0b00000, 0b00000, 0b10001, 0b01010, 0b00100, 0b01010, 0b10001],
    "y": [0b00000, 0b10001, 0b10001, 0b01111, 0b00001, 0b10001, 0b01110],
    "z": [0b00000, 0b00000, 0b11111, 0b00010, 0b00100, 0b01000, 0b11111],
    "{": [0b00110, 0b00100, 0b00100, 0b01000, 0b00100, 0b00100, 0b00110],
    "|": [0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100],
    "}": [0b01100, 0b00100, 0b00100, 0b00010, 0b00100, 0b00100, 0b01100],
    "~": [0b00000, 0b00000, 0b01000, 0b10101, 0b00010, 0b00000, 0b00000],
}

_CHAR_W = 5
_CHAR_H = 7
_CHAR_SPACING = 1  # gap between characters


def _parse_color(color: str | list | tuple) -> Pixel:
    """Accept '#RRGGBB', 'RRGGBB', or [R,G,B] / (R,G,B)."""
    if isinstance(color, (list, tuple)):
        return (int(color[0]), int(color[1]), int(color[2]))
    c = color.lstrip("#")
    if len(c) == 6:
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
    if len(c) == 3:
        return (int(c[0] * 2, 16), int(c[1] * 2, 16), int(c[2] * 2, 16))
    raise ValueError(f"Unrecognised color format: {color!r}")


class Matrix:
    """16×16 LED matrix with serpentine-aware coordinate mapping."""

    def __init__(self, width: int = 16, height: int = 16, serpentine: bool = False):
        self.width = width
        self.height = height
        self.serpentine = serpentine
        self.pixels: list[Pixel] = [(0, 0, 0)] * (width * height)

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _xy_to_idx(self, x: int, y: int) -> int:
        px = (self.width - 1 - x) if (self.serpentine and y % 2 == 1) else x
        return y * self.width + px

    def set_pixel(self, x: int, y: int, color: Pixel) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.pixels[self._xy_to_idx(x, y)] = color

    def get_pixel(self, x: int, y: int) -> Pixel:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.pixels[self._xy_to_idx(x, y)]
        return (0, 0, 0)

    def clear(self) -> None:
        self.pixels = [(0, 0, 0)] * (self.width * self.height)

    def fill(self, color: Pixel) -> None:
        self.pixels = [color] * (self.width * self.height)

    # ------------------------------------------------------------------
    # Drawing primitives
    # ------------------------------------------------------------------

    def draw_rect(
        self,
        x: int, y: int,
        w: int, h: int,
        color: Pixel,
        filled: bool = True,
    ) -> None:
        for py in range(y, y + h):
            for px in range(x, x + w):
                if filled or px in (x, x + w - 1) or py in (y, y + h - 1):
                    self.set_pixel(px, py, color)

    def draw_line(
        self,
        x0: int, y0: int,
        x1: int, y1: int,
        color: Pixel,
    ) -> None:
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            self.set_pixel(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def draw_circle(
        self, cx: int, cy: int, radius: int, color: Pixel, filled: bool = False
    ) -> None:
        for y in range(self.height):
            for x in range(self.width):
                d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                if filled:
                    if d <= radius:
                        self.set_pixel(x, y, color)
                else:
                    if abs(d - radius) < 0.75:
                        self.set_pixel(x, y, color)

    def draw_gradient(
        self,
        color_start: Pixel,
        color_end: Pixel,
        direction: str = "horizontal",
    ) -> None:
        steps = self.width if direction == "horizontal" else self.height
        for i in range(steps):
            t = i / max(steps - 1, 1)
            c = tuple(int(a + (b - a) * t) for a, b in zip(color_start, color_end))
            for j in range(self.height if direction == "horizontal" else self.width):
                x, y = (i, j) if direction == "horizontal" else (j, i)
                self.set_pixel(x, y, c)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Text rendering (uses embedded 5×7 bitmap font)
    # ------------------------------------------------------------------

    def _render_char(self, ch: str, x: int, y: int, color: Pixel) -> None:
        glyph = _FONT_5X7.get(ch, _FONT_5X7.get("?", [0] * 7))
        for row_idx, bits in enumerate(glyph):
            for col_idx in range(_CHAR_W):
                if bits & (1 << (_CHAR_W - 1 - col_idx)):
                    self.set_pixel(x + col_idx, y + row_idx, color)

    def render_text_frame(
        self,
        text: str,
        x_offset: int,
        color: Pixel,
        bg: Pixel = (0, 0, 0),
    ) -> None:
        """Render text starting at x_offset (can be negative for scrolling).

        y is fixed at 4 to vertically centre 7px glyphs in 16px height.
        """
        self.fill(bg)
        y = (self.height - _CHAR_H) // 2
        for i, ch in enumerate(text):
            cx = x_offset + i * (_CHAR_W + _CHAR_SPACING)
            if -_CHAR_W <= cx < self.width:
                self._render_char(ch, cx, y, color)

    def text_width(self, text: str) -> int:
        """Pixel width of a string."""
        return len(text) * (_CHAR_W + _CHAR_SPACING) - _CHAR_SPACING

    # ------------------------------------------------------------------
    # Image rendering
    # ------------------------------------------------------------------

    def load_pil_image(self, img: Image.Image) -> None:
        """Resize and map a PIL image onto the matrix (handles serpentine)."""
        img = img.convert("RGB").resize(
            (self.width, self.height), Image.Resampling.LANCZOS
        )
        for y in range(self.height):
            for x in range(self.width):
                self.set_pixel(x, y, img.getpixel((x, y)))

    async def load_image_url(self, url: str) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
            r.raise_for_status()
        img = Image.open(io.BytesIO(r.content))
        self.load_pil_image(img)

    def load_image_path(self, path: str) -> None:
        self.load_pil_image(Image.open(path))

    def load_image_bytes(self, data: bytes) -> None:
        self.load_pil_image(Image.open(io.BytesIO(data)))

    # ------------------------------------------------------------------
    # Scroll helper: generate all frames for a text scroll
    # ------------------------------------------------------------------

    def text_scroll_frames(
        self,
        text: str,
        color: Pixel,
        bg: Pixel = (0, 0, 0),
        start_x: int | None = None,
    ) -> list[list[Pixel]]:
        """Return a list of pixel snapshots, one per scroll step."""
        total_w = self.text_width(text)
        start = self.width if start_x is None else start_x
        end = -total_w
        frames: list[list[Pixel]] = []
        for offset in range(start, end - 1, -1):
            self.render_text_frame(text, offset, color, bg)
            frames.append(self.pixels.copy())
        return frames

    # ------------------------------------------------------------------
    # Pattern generators
    # ------------------------------------------------------------------

    def checkerboard(self, color_a: Pixel, color_b: Pixel, size: int = 2) -> None:
        for y in range(self.height):
            for x in range(self.width):
                c = color_a if ((x // size + y // size) % 2 == 0) else color_b
                self.set_pixel(x, y, c)

    def rainbow(self) -> None:
        """Horizontal rainbow across the matrix."""
        import colorsys
        for x in range(self.width):
            h = x / self.width
            r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
            for y in range(self.height):
                self.set_pixel(x, y, (int(r * 255), int(g * 255), int(b * 255)))

    def progress_bar(
        self,
        value: float,        # 0.0 – 1.0
        color_fill: Pixel = (0, 200, 0),
        color_bg: Pixel = (20, 20, 20),
        border_color: Pixel | None = (100, 100, 100),
        height: int = 4,
    ) -> None:
        """Draw a horizontal progress bar centred vertically."""
        y_start = (self.height - height) // 2
        fill_w = max(0, min(self.width, int(value * self.width)))
        for y in range(y_start, y_start + height):
            for x in range(self.width):
                on_border = (
                    border_color is not None
                    and (
                        x in (0, self.width - 1)
                        or y in (y_start, y_start + height - 1)
                    )
                )
                if on_border:
                    self.set_pixel(x, y, border_color)  # type: ignore[arg-type]
                elif x < fill_w:
                    self.set_pixel(x, y, color_fill)
                else:
                    self.set_pixel(x, y, color_bg)


# ---------------------------------------------------------------------------
# High-level send helpers
# ---------------------------------------------------------------------------


async def push(matrix: Matrix, client: "WLEDClient", brightness: int | None = None) -> None:
    await client.set_pixels(matrix.pixels, brightness)


async def scroll_text(
    matrix: Matrix,
    client: "WLEDClient",
    text: str,
    color: Pixel,
    bg: Pixel = (0, 0, 0),
    speed_ms: int = 60,
    brightness: int | None = None,
) -> None:
    """Stream scrolling-text frames to the device."""
    frames = matrix.text_scroll_frames(text, color, bg)
    for frame in frames:
        matrix.pixels = frame
        await push(matrix, client, brightness)
        await asyncio.sleep(speed_ms / 1000)
