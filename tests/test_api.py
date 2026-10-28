"""End-to-end API tests: upload -> create scene -> play -> end_scene -> stop."""

from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf


def _wav_bytes(seconds: float = 0.5, sample_rate: int = 48_000) -> bytes:
    n = int(seconds * sample_rate)
    data = (np.sin(2 * np.pi * 440 * np.arange(n) / sample_rate) * 0.2).astype(np.float32)
    stereo = np.column_stack([data, data])
    buf = io.BytesIO()
    sf.write(buf, stereo, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


# ---- Tests -------------------------------------------------------------------


def test_upload_and_list(client):
    wav = _wav_bytes()
    resp = client.post("/api/uploads", files={"file": ("battle.wav", wav, "audio/wav")})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["original_name"] == "battle.wav"
    assert body["sample_rate"] == 48_000
    assert body["channels"] == 2

    listed = client.get("/api/uploads").json()
    assert len(listed) == 1
    assert listed[0]["id"] == body["id"]


def test_reject_unsupported_extension(client):
    resp = client.post("/api/uploads", files={"file": ("badge.exe", b"MZ...", "application/octet-stream")})
    assert resp.status_code == 400


def test_create_scene_and_retrieve(client):
    audio = client.post("/api/uploads", files={"file": ("m.wav", _wav_bytes(), "audio/wav")}).json()
    payload = {
        "name": "Forest",
        "layers": [{"audio_file_id": audio["id"], "loop": True, "volume": 0.7}],
        "on_end": {"type": "return_previous"},
    }
    scene = client.post("/api/scenes", json=payload).json()
    assert scene["name"] == "Forest"
    assert len(scene["layers"]) == 1

    fetched = client.get(f"/api/scenes/{scene['id']}").json()
    assert fetched["id"] == scene["id"]


def test_create_scene_rejects_missing_audio_reference(client):
    from uuid import uuid4

    response = client.post(
        "/api/scenes",
        json={"name": "broken", "layers": [{"audio_file_id": str(uuid4())}]},
    )
    assert response.status_code == 422
    assert "audio files not found" in response.json()["detail"]


def test_transition_rejects_missing_target_and_blocks_target_deletion(client):
    from uuid import uuid4

    source = client.post("/api/scenes", json={"name": "source"}).json()
    target = client.post("/api/scenes", json={"name": "target"}).json()

    missing = client.patch(
        f"/api/scenes/{source['id']}/on_end",
        json={"on_end": {"type": "goto", "scene_id": str(uuid4())}},
    )
    assert missing.status_code == 422
    assert "transition target scene not found" in missing.json()["detail"]

    linked = client.patch(
        f"/api/scenes/{source['id']}/on_end",
        json={"on_end": {"type": "goto", "scene_id": target["id"]}},
    )
    assert linked.status_code == 200
    blocked = client.delete(f"/api/scenes/{target['id']}")
    assert blocked.status_code == 409
    assert "referenced by transition" in blocked.json()["detail"]


def test_play_stop_end_scene_flow(client):
    audio_id = client.post("/api/uploads", files={"file": ("m.wav", _wav_bytes(), "audio/wav")}).json()["id"]
    exploration = client.post("/api/scenes", json={
        "name": "Exploration",
        "layers": [{"audio_file_id": audio_id}],
        "on_end": {"type": "return_previous"},
    }).json()
    combat = client.post("/api/scenes", json={
        "name": "Combat",
        "layers": [{"audio_file_id": audio_id}],
        "on_end": {"type": "return_previous"},
    }).json()

    assert client.post("/api/playback/play", json={"scene_id": exploration["id"]}).status_code == 202
    assert client.post("/api/playback/play", json={"scene_id": combat["id"]}).status_code == 202

    state = client.get("/api/playback/state").json()
    assert state["current_scene_id"] == combat["id"]
    assert state["previous_scene_id"] == exploration["id"]

    # end_scene should trigger return_previous -> exploration becomes current again
    assert client.post("/api/playback/end_scene").status_code == 202
    state = client.get("/api/playback/state").json()
    assert state["current_scene_id"] == exploration["id"]

    assert client.post("/api/playback/stop").status_code == 202


def test_play_missing_scene_returns_404(client):
    from uuid import uuid4
    resp = client.post("/api/playback/play", json={"scene_id": str(uuid4())})
    assert resp.status_code == 404


def test_delete_audio_used_by_scene_conflicts(client):
    audio_id = client.post("/api/uploads", files={"file": ("m.wav", _wav_bytes(), "audio/wav")}).json()["id"]
    client.post("/api/scenes", json={"name": "s", "layers": [{"audio_file_id": audio_id}]})
    resp = client.delete(f"/api/uploads/{audio_id}")
    assert resp.status_code == 409


def test_master_volume(client):
    resp = client.post("/api/playback/volume", json={"target": "master", "volume": 0.3})
    assert resp.status_code == 202
    state = client.get("/api/playback/state").json()
    assert state["master_volume"] == pytest.approx(0.3)


def test_websocket_receives_state_snapshot(client):
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        assert first["type"] == "state"
        assert "master_volume" in first


def test_scene_position_patch_persists(client):
    audio_id = client.post("/api/uploads", files={"file": ("m.wav", _wav_bytes(), "audio/wav")}).json()["id"]
    scene = client.post("/api/scenes", json={
        "name": "positioned", "layers": [{"audio_file_id": audio_id}],
    }).json()
    assert scene["graph_x"] is None
    assert scene["graph_y"] is None

    resp = client.patch(f"/api/scenes/{scene['id']}/position", json={"x": 120.5, "y": -80.0})
    assert resp.status_code == 204

    fetched = client.get(f"/api/scenes/{scene['id']}").json()
    assert fetched["graph_x"] == 120.5
    assert fetched["graph_y"] == -80.0


def test_on_end_patch_creates_edge(client):
    audio_id = client.post("/api/uploads", files={"file": ("m.wav", _wav_bytes(), "audio/wav")}).json()["id"]
    source = client.post("/api/scenes", json={"name": "src", "layers": [{"audio_file_id": audio_id}]}).json()
    target = client.post("/api/scenes", json={"name": "tgt", "layers": [{"audio_file_id": audio_id}]}).json()

    # Draw edge: source.on_end -> goto target
    resp = client.patch(f"/api/scenes/{source['id']}/on_end",
                        json={"on_end": {"type": "goto", "scene_id": target["id"]}})
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["on_end"]["type"] == "goto"
    assert updated["on_end"]["scene_id"] == target["id"]

    # Erase edge: back to return_previous
    resp = client.patch(f"/api/scenes/{source['id']}/on_end",
                        json={"on_end": {"type": "return_previous"}})
    assert resp.json()["on_end"]["type"] == "return_previous"
