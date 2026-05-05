"""WLED HTTP/JSON API client."""
from __future__ import annotations

import httpx


class WLEDError(Exception):
    pass


class WLEDClient:
    def __init__(self, host: str, port: int = 80):
        self.base_url = f"http://{host}:{port}"
        self._client = httpx.AsyncClient(timeout=10.0)

    async def get_info(self) -> dict:
        r = await self._client.get(f"{self.base_url}/json/info")
        r.raise_for_status()
        return r.json()

    async def get_state(self) -> dict:
        r = await self._client.get(f"{self.base_url}/json/state")
        r.raise_for_status()
        return r.json()

    async def get_effects(self) -> list[str]:
        r = await self._client.get(f"{self.base_url}/json/eff")
        r.raise_for_status()
        return r.json()

    async def get_palettes(self) -> list[str]:
        r = await self._client.get(f"{self.base_url}/json/pal")
        r.raise_for_status()
        return r.json()

    async def set_state(self, state: dict) -> dict:
        r = await self._client.post(f"{self.base_url}/json/state", json=state)
        r.raise_for_status()
        return r.json()

    async def set_pixels(
        self,
        pixels: list[tuple[int, int, int]],
        brightness: int | None = None,
    ) -> dict:
        """Push a flat list of 256 (R,G,B) tuples as a full-frame pixel update.

        Uses effect 0 (Solid) so the effect engine doesn't override the frame.
        """
        colors = [f"{r:02X}{g:02X}{b:02X}" for r, g, b in pixels]
        state: dict = {
            "on": True,
            "seg": [{"i": colors, "fx": 0}],
        }
        if brightness is not None:
            state["bri"] = max(0, min(255, brightness))
        return await self.set_state(state)

    async def set_effect(
        self,
        effect_id: int,
        palette_id: int = 0,
        speed: int = 128,
        intensity: int = 128,
        color: tuple[int, int, int] = (255, 255, 255),
        brightness: int | None = None,
    ) -> dict:
        r, g, b = color
        state: dict = {
            "on": True,
            "seg": [
                {
                    "fx": effect_id,
                    "pal": palette_id,
                    "sx": speed,
                    "ix": intensity,
                    "col": [[r, g, b]],
                }
            ],
        }
        if brightness is not None:
            state["bri"] = max(0, min(255, brightness))
        return await self.set_state(state)

    async def set_power(self, on: bool) -> dict:
        return await self.set_state({"on": on})

    async def set_brightness(self, brightness: int) -> dict:
        return await self.set_state({"bri": max(0, min(255, brightness))})

    async def close(self) -> None:
        await self._client.aclose()
