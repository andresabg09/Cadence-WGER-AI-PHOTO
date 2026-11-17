"""cadence's own food pictures: every listed one exists, has a free licence and an author (they ask to be credited)."""

import json

from fastapi.testclient import TestClient

from app import foodphotos, main


def test_every_listed_picture_is_shippable():
    raw = json.loads(foodphotos.DATA.read_text(encoding="utf-8"))
    assert isinstance(raw, list)
    for item in raw:
        assert foodphotos.FILE.fullmatch(item["file"]), item
        assert (foodphotos.STATIC / item["file"]).is_file(), item["file"]
        assert foodphotos.LICENCES.match(item["license"]), item
        assert item["author"] and item["names"], item
        assert item["source"].startswith("https://commons.wikimedia.org/"), item
    assert len(foodphotos.entries()) == len(raw)  # nothing listed is silently dropped


def test_entries_without_licence_or_credit_are_left_out(tmp_path, monkeypatch):
    data = tmp_path / "food_photos.json"
    data.write_text(json.dumps([
        {"file": "arepa.jpg", "names": ["arepa"], "author": "A", "license": "CC BY-SA 4.0", "source": "https://commons.wikimedia.org/wiki/File:A.jpg"},
        {"file": "x.jpg", "names": ["x"], "author": "B", "license": "All rights reserved", "source": "https://commons.wikimedia.org/wiki/File:X.jpg"},
        {"file": "y.jpg", "names": ["y"], "author": "", "license": "CC0", "source": "https://commons.wikimedia.org/wiki/File:Y.jpg"},
        {"file": "../z.jpg", "names": ["z"], "author": "C", "license": "CC0", "source": "https://commons.wikimedia.org/wiki/File:Z.jpg"},
    ]), encoding="utf-8")
    monkeypatch.setattr(foodphotos, "DATA", data)
    foodphotos.entries.cache_clear()
    try:
        assert [e["file"] for e in foodphotos.entries()] == ["arepa.jpg"]
        assert foodphotos.for_app() == [{"names": ["arepa"], "src": "static/food-photos/arepa.jpg"}]
        assert foodphotos.credits()[0]["license"] == "CC BY-SA 4.0"
    finally:
        foodphotos.entries.cache_clear()


def test_credits_and_food_photos_need_a_session():
    http = TestClient(main.app)
    assert http.get("/api/photo-credits").status_code == 200  # signed in by the test fixture
    body = http.get("/api/food-photos").json()
    assert "names" in body and "local" in body
