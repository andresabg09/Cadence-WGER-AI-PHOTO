"""Small local store for what wger has no place for: a note per diary entry and the photos.

wger stays the source of truth for food, diary and goals. This SQLite file (on the
`cadence_data` volume, so it survives redeploys) only keeps the extras that make a past
record readable again: the user's note, the crop of each ingredient and the plate photo.
"""

import base64
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from .config import settings

_DATA_URL = re.compile(r"^data:image/(?:jpeg|jpg|png|webp);base64,(.+)$", re.DOTALL)
MAX_IMAGE_BYTES = 6 * 1024 * 1024


def _db_path() -> Path:
    path = Path(settings.data_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path / "cadence.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=10)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS entry_meta ("
        " entry_id TEXT PRIMARY KEY, note TEXT, crop BLOB, plate_key TEXT, box TEXT)"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS plates (key TEXT PRIMARY KEY, data BLOB NOT NULL)")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(entry_meta)")}
    if "logged_on" not in columns:  # day the entry was really registered (streaks need it)
        conn.execute("ALTER TABLE entry_meta ADD COLUMN logged_on TEXT")
    return conn


def decode_image(data_url: str | None) -> bytes | None:
    """Bytes of a base64 data URL image, or None if it isn't a (reasonably sized) image."""
    match = _DATA_URL.match(data_url or "")
    if not match:
        return None
    try:
        raw = base64.b64decode(match.group(1), validate=False)
    except ValueError:
        return None
    return raw if 0 < len(raw) <= MAX_IMAGE_BYTES else None


def get_meta(entry_ids: list[str]) -> dict[str, dict]:
    if not entry_ids:
        return {}
    marks = ",".join("?" * len(entry_ids))
    with closing(_connect()) as conn:
        rows = conn.execute(
            f"SELECT entry_id, note, crop IS NOT NULL, plate_key, box FROM entry_meta WHERE entry_id IN ({marks})",
            [str(i) for i in entry_ids],
        ).fetchall()
    return {
        row[0]: {"note": row[1] or None, "has_crop": bool(row[2]), "plate_key": row[3],
                 "box": json.loads(row[4]) if row[4] else None}
        for row in rows
    }


def set_note(entry_id: str, note: str | None) -> None:
    clean = (note or "").strip()[:2000]
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT OR IGNORE INTO entry_meta (entry_id) VALUES (?)", (str(entry_id),))
        conn.execute("UPDATE entry_meta SET note = ? WHERE entry_id = ?", (clean or None, str(entry_id)))


def set_media(entry_id: str, crop: bytes | None, plate_key: str | None, box: list[float] | None) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT OR IGNORE INTO entry_meta (entry_id) VALUES (?)", (str(entry_id),))
        if crop:
            conn.execute("UPDATE entry_meta SET crop = ? WHERE entry_id = ?", (crop, str(entry_id)))
        if plate_key:
            conn.execute(
                "UPDATE entry_meta SET plate_key = ?, box = ? WHERE entry_id = ?",
                (plate_key, json.dumps(box) if box else None, str(entry_id)),
            )


def put_plate(key: str, data: bytes) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT OR REPLACE INTO plates (key, data) VALUES (?, ?)", (key, data))


def get_crop(entry_id: str) -> bytes | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT crop FROM entry_meta WHERE entry_id = ?", (str(entry_id),)).fetchone()
    return row[0] if row and row[0] else None


def get_plate(key: str) -> bytes | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT data FROM plates WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def delete_entry(entry_id: str) -> None:
    """Forget an entry's extras; a plate photo goes with its last entry."""
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM entry_meta WHERE entry_id = ?", (str(entry_id),))
        conn.execute("DELETE FROM plates WHERE key NOT IN (SELECT plate_key FROM entry_meta WHERE plate_key IS NOT NULL)")


def set_logged_on(entry_ids: list[str], day: str) -> None:
    """Remember the real day each entry was registered (not the day the food was eaten)."""
    with closing(_connect()) as conn, conn:
        for entry_id in entry_ids:
            conn.execute("INSERT OR IGNORE INTO entry_meta (entry_id) VALUES (?)", (str(entry_id),))
            conn.execute("UPDATE entry_meta SET logged_on = ? WHERE entry_id = ?", (day, str(entry_id)))


def get_logged_on(entry_ids: list[str]) -> dict[str, str]:
    """entry id -> ISO day it was registered; entries registered before this existed are absent."""
    found: dict[str, str] = {}
    ids = [str(i) for i in entry_ids]
    with closing(_connect()) as conn:
        for start in range(0, len(ids), 500):  # SQLite caps the number of ? in one statement
            chunk = ids[start:start + 500]
            marks = ",".join("?" * len(chunk))
            for entry_id, day in conn.execute(
                f"SELECT entry_id, logged_on FROM entry_meta WHERE logged_on IS NOT NULL AND entry_id IN ({marks})", chunk
            ):
                found[entry_id] = day
    return found
