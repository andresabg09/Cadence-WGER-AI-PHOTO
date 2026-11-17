"""Pictures of foods that cadence ships itself (static/food-photos/), for foods TheMealDB has no picture of.

Each one was chosen by hand from Wikimedia Commons under a free licence (CC0, public domain, CC BY or CC BY-SA) and the list
keeps its author, licence and source so the app can credit them (Ajustes -> Créditos de fotos), as those licences require.
A food with no entry keeps no picture: never a "close enough" one.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data" / "food_photos.json"
STATIC = Path(__file__).parent.parent / "static" / "food-photos"
LICENCES = re.compile(r"^(CC0( 1\.0)?|Public domain|CC BY(-SA)? [0-9.]+( [a-z]+)?)$", re.IGNORECASE)
FILE = re.compile(r"^[a-z0-9_-]+\.jpg$")


@lru_cache(maxsize=1)
def entries() -> list[dict]:
    try:
        raw = json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for item in raw if isinstance(raw, list) else []:
        if (isinstance(item, dict) and FILE.fullmatch(str(item.get("file") or "")) and LICENCES.match(str(item.get("license") or ""))
                and item.get("names") and item.get("author") and str(item.get("source") or "").startswith("https://commons.wikimedia.org/")):
            out.append(item)
    return out


def for_app() -> list[dict]:
    """What the screens need to show the pictures: the names that mean this food and where the picture is."""
    return [{"names": list(item["names"]), "src": f"static/food-photos/{item['file']}"} for item in entries()]


def credits() -> list[dict]:
    return [{"food": item["names"][0], "title": item.get("title") or "", "author": item["author"], "license": item["license"],
             "license_url": item.get("license_url") or "", "source": item["source"]} for item in entries()]
