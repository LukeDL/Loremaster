"""Populate the running server with two demo scenes so the UI has content to test.

Usage: `uv run python seed_demo.py` (server must be up on 127.0.0.1:8765).
"""

from __future__ import annotations

import io
import sys

import httpx
import numpy as np
import soundfile as sf

BASE = "http://127.0.0.1:8765"
SR = 48_000


def make_tone(freq: float, seconds: float, amp: float = 0.15) -> bytes:
    """Generate a loop-friendly sine tone as WAV bytes."""
    period = SR / freq
    n_periods = max(1, int(seconds * freq))
    n = int(round(n_periods * period))
    t = np.arange(n, dtype=np.float32) / SR
    wave = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    stereo = np.column_stack([wave, wave])
    buf = io.BytesIO()
    sf.write(buf, stereo, SR, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def upload(client: httpx.Client, name: str, wav: bytes) -> str:
    r = client.post("/api/uploads", files={"file": (name, wav, "audio/wav")})
    r.raise_for_status()
    return r.json()["id"]


def create_scene(client: httpx.Client, payload: dict) -> dict:
    r = client.post("/api/scenes", json=payload)
    r.raise_for_status()
    return r.json()


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=10.0) as client:
        existing = client.get("/api/scenes").json()
        if existing:
            print(f"scenes already exist ({len(existing)}) — not seeding again")
            return 0

        pad_id = upload(client, "pad_220hz.wav", make_tone(220, 4.0, 0.15))
        amb_id = upload(client, "ambient_330hz.wav", make_tone(330, 3.0, 0.08))
        drums_id = upload(client, "drums_110hz.wav", make_tone(110, 2.0, 0.25))
        brass_id = upload(client, "brass_440hz.wav", make_tone(440, 2.5, 0.12))

        exploration = create_scene(client, {
            "name": "Exploração — Floresta",
            "description": "Cena de exemplo (tons sintéticos)",
            "layers": [
                {"audio_file_id": pad_id, "loop": True, "volume": 0.8, "fade_in_ms": 1500, "fade_out_ms": 1500},
                {"audio_file_id": amb_id, "loop": True, "volume": 0.6, "fade_in_ms": 1500, "fade_out_ms": 1500},
            ],
            "on_end": {"type": "return_previous"},
        })
        combat = create_scene(client, {
            "name": "Combate — genérico",
            "description": "Loop de batalha; fim de combate retorna à cena anterior",
            "layers": [
                {"audio_file_id": drums_id, "loop": True, "volume": 0.9, "fade_in_ms": 800, "fade_out_ms": 1200},
                {"audio_file_id": brass_id, "loop": True, "volume": 0.7, "fade_in_ms": 800, "fade_out_ms": 1200},
            ],
            "on_end": {"type": "return_previous"},
        })
        # Put demo scenes on the map by default so /map opens with something visible
        for scene_id in (exploration["id"], combat["id"]):
            client.patch(f"/api/scenes/{scene_id}/map", json={"is_on_map": True})

        print(f"created scenes: {exploration['name']!r}, {combat['name']!r}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
