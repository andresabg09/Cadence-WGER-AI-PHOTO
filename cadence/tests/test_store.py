import base64
import os
import tempfile

os.environ.setdefault("GEMINI_API_KEY", "x")
os.environ.setdefault("WGER_API_TOKEN", "x")

import pytest
from fastapi.testclient import TestClient

from app import main, store
from app.config import settings

PNG = "data:image/png;base64," + base64.b64encode(
    base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")
).decode()


class OwnPlanWger:
    """Every entry asked about lives in the signed-in user's plan (wger plan 1)."""

    def get_diary_entry(self, entry_id): return {"id": entry_id, "plan": 1}
    def close(self): pass


def test_note_and_media_roundtrip_and_cleanup(monkeypatch):
    monkeypatch.setattr(main, "get_wger_client", lambda: OwnPlanWger())
    http = TestClient(main.app, raise_server_exceptions=False)
    assert http.put("/api/diary/e1/note", json={"note": "  con poca sal "}).status_code == 200
    body = {"plate_id": "e1", "photos": [PNG], "items": [{"entry_id": "e1", "crop": PNG, "photo": 0, "box": [0.1, 0.2, 0.3, 0.4]}]}
    assert http.post("/api/entry-media", json=body).json() == {"saved": 1}

    meta = store.get_meta(["e1", "zz"])
    assert meta["e1"] == {"note": "con poca sal", "has_crop": True, "plate_key": "1-e1:0", "box": [0.1, 0.2, 0.3, 0.4], "liquid": None}
    assert "zz" not in meta
    assert http.get("/api/media/crop/e1").status_code == 200
    assert http.get("/api/media/plate/1-e1:0").headers["content-type"] == "image/jpeg"
    assert http.get("/api/media/crop/nope").status_code == 404

    store.delete_entry("e1")
    assert store.get_meta(["e1"]) == {}
    assert http.get("/api/media/plate/1-e1:0").status_code == 404


def test_garbage_images_are_ignored_and_empty_note_clears():
    assert store.decode_image("not an image") is None
    assert store.decode_image("data:text/html;base64,AAAA") is None
    store.set_note("e2", "hola")
    store.set_note("e2", "   ")
    assert store.get_meta(["e2"])["e2"]["note"] is None


def test_food_added_by_hand_joins_the_plate_group(monkeypatch):
    monkeypatch.setattr(main, "get_wger_client", lambda: OwnPlanWger())
    http = TestClient(main.app, raise_server_exceptions=False)
    body = {"plate_id": "g1", "photos": [PNG], "items": [
        {"entry_id": "g1", "crop": PNG, "photo": 0, "box": [0.1, 0.2, 0.3, 0.4]},
        {"entry_id": "g2", "crop": None, "photo": None, "box": [0.5, 0.5, 0.1, 0.1]},
    ]}
    assert http.post("/api/entry-media", json=body).json() == {"saved": 2}
    meta = store.get_meta(["g1", "g2"])
    assert meta["g1"]["plate_key"] == meta["g2"]["plate_key"] == "1-g1:0"
    assert meta["g2"]["box"] is None  # it is not located in the photo


def test_expired_reset_code_is_refused():
    created = store.create_user("late@example.com", "Late", "x", None, True)
    uid = (created[0] if isinstance(created, tuple) else created).id
    store.create_reset(uid, "hash1", "2000-01-01T00:00:00+00:00")
    assert store.consume_reset(uid, "hash1") is False
