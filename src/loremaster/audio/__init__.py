"""Audio engine: mixer NumPy próprio para gapless loop e crossfade sample-accurate."""

from loremaster.audio.engine import AudioEngine
from loremaster.audio.layer import Layer, LayerSpec
from loremaster.audio.loader import AudioLoader
from loremaster.audio.scene_player import ScenePlayer, SceneSpec

__all__ = [
    "AudioEngine",
    "AudioLoader",
    "Layer",
    "LayerSpec",
    "ScenePlayer",
    "SceneSpec",
]
