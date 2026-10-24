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
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import settings

_DATA_URL = re.compile(r"^data:image/(?:jpeg|jpg|png|webp);base64,(.+)$", re.DOTALL)
MAX_IMAGE_BYTES = 6 * 1024 * 1024


_ACCOUNT_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  is_admin INTEGER NOT NULL DEFAULT 0,
  plan_id TEXT,
  sex TEXT, birthdate TEXT, height_cm REAL, activity TEXT, goal TEXT, target_weight_kg REAL,
  goal_kcal REAL, goal_protein REAL, goal_carbs REAL, goal_fat REAL,
  onboarded INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invites (
  code TEXT PRIMARY KEY, note TEXT, created_by INTEGER, created_at TEXT NOT NULL, used_by INTEGER, used_at TEXT
);
CREATE TABLE IF NOT EXISTS resets (
  code_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS custom_foods (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, name TEXT NOT NULL,
  kcal REAL NOT NULL, protein REAL NOT NULL DEFAULT 0, carbs REAL NOT NULL DEFAULT 0, fat REAL NOT NULL DEFAULT 0,
  barcode TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS local_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, food_id INTEGER NOT NULL,
  grams REAL NOT NULL, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workouts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, day TEXT NOT NULL, kind TEXT NOT NULL,
  minutes INTEGER NOT NULL, kcal REAL NOT NULL, note TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS weights (
  user_id INTEGER NOT NULL, day TEXT NOT NULL, kg REAL NOT NULL, PRIMARY KEY (user_id, day)
);
CREATE TABLE IF NOT EXISTS usage (
  user_id INTEGER NOT NULL, day TEXT NOT NULL, analyses INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (user_id, day)
);
"""


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
    conn.executescript(_ACCOUNT_SCHEMA)
    for table, column, kind in (
        ("entry_meta", "logged_on", "TEXT"),  # day the entry was really registered (streaks need it)
        ("entry_meta", "user_id", "INTEGER"),  # whose entry it is
        ("plates", "user_id", "INTEGER"),
    ):
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
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


def set_note(entry_id: str, note: str | None, user_id: int | None = None) -> None:
    clean = (note or "").strip()[:2000]
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT OR IGNORE INTO entry_meta (entry_id) VALUES (?)", (str(entry_id),))
        conn.execute("UPDATE entry_meta SET note = ?, user_id = COALESCE(user_id, ?) WHERE entry_id = ?",
                     (clean or None, user_id, str(entry_id)))


def set_media(entry_id: str, crop: bytes | None, plate_key: str | None, box: list[float] | None,
              user_id: int | None = None) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT OR IGNORE INTO entry_meta (entry_id) VALUES (?)", (str(entry_id),))
        conn.execute("UPDATE entry_meta SET user_id = COALESCE(user_id, ?) WHERE entry_id = ?", (user_id, str(entry_id)))
        if crop:
            conn.execute("UPDATE entry_meta SET crop = ? WHERE entry_id = ?", (crop, str(entry_id)))
        if plate_key:
            conn.execute(
                "UPDATE entry_meta SET plate_key = ?, box = ? WHERE entry_id = ?",
                (plate_key, json.dumps(box) if box else None, str(entry_id)),
            )


def put_plate(key: str, data: bytes, user_id: int | None = None) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT OR REPLACE INTO plates (key, data, user_id) VALUES (?, ?, ?)", (key, data, user_id))


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


def set_logged_on(entry_ids: list[str], day: str, user_id: int | None = None) -> None:
    """Remember the real day each entry was registered (not the day the food was eaten) and whose it is."""
    with closing(_connect()) as conn, conn:
        for entry_id in entry_ids:
            conn.execute("INSERT OR IGNORE INTO entry_meta (entry_id) VALUES (?)", (str(entry_id),))
            conn.execute("UPDATE entry_meta SET logged_on = ?, user_id = COALESCE(user_id, ?) WHERE entry_id = ?",
                         (day, user_id, str(entry_id)))


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


# ---------------------------------------------------------------- accounts

SESSION_DAYS = 60


@dataclass
class User:
    id: int
    email: str
    name: str
    is_admin: bool
    plan_id: str | None
    sex: str | None = None
    birthdate: str | None = None
    height_cm: float | None = None
    activity: str | None = None
    goal: str | None = None
    target_weight_kg: float | None = None
    goal_kcal: float | None = None
    goal_protein: float | None = None
    goal_carbs: float | None = None
    goal_fat: float | None = None
    onboarded: bool = False
    created_at: str = field(default="")


_USER_COLUMNS = ("id, email, name, is_admin, plan_id, sex, birthdate, height_cm, activity, goal, target_weight_kg, "
                 "goal_kcal, goal_protein, goal_carbs, goal_fat, onboarded, created_at")
_PROFILE_FIELDS = {"name", "sex", "birthdate", "height_cm", "activity", "goal", "target_weight_kg", "goal_kcal",
                   "goal_protein", "goal_carbs", "goal_fat", "onboarded", "plan_id", "password_hash"}


def _user(row) -> User | None:
    if row is None:
        return None
    values = list(row)
    values[3] = bool(values[3])
    values[15] = bool(values[15])
    return User(*values)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def count_users() -> int:
    with closing(_connect()) as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def create_user(email: str, name: str, password_hash: str, invite: str | None, allow_open: bool,
                first_user_email: str | None = None) -> tuple[User | None, str | None]:
    """Create an account. Returns (user, None) or (None, reason).

    The very first account is the administrator (it needs no invite, and, when `first_user_email`
    is set, must be that address). Everyone else needs an unused invite code, unless registration
    is open. The checks and the insert are one transaction, so two people cannot race for a code.
    """
    with closing(_connect()) as conn:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")
        try:
            if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                conn.execute("ROLLBACK")
                return None, "exists"
            first = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
            if first and first_user_email and email != first_user_email.strip().lower():
                conn.execute("ROLLBACK")
                return None, "not_admin_email"
            invite_row = None
            if not first and not allow_open:
                invite_row = conn.execute(
                    "SELECT code FROM invites WHERE code = ? AND used_by IS NULL", ((invite or "").strip().upper(),)
                ).fetchone()
                if invite_row is None:
                    conn.execute("ROLLBACK")
                    return None, "bad_invite"
            cursor = conn.execute(
                "INSERT INTO users (email, name, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?, ?)",
                (email, name, password_hash, 1 if first else 0, _now()),
            )
            user_id = cursor.lastrowid
            if invite_row is not None:
                conn.execute("UPDATE invites SET used_by = ?, used_at = ? WHERE code = ?", (user_id, _now(), invite_row[0]))
            if first:  # what was saved before accounts existed belongs to the administrator
                conn.execute("UPDATE entry_meta SET user_id = ? WHERE user_id IS NULL", (user_id,))
                conn.execute("UPDATE plates SET user_id = ? WHERE user_id IS NULL", (user_id,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return get_user(user_id), None


def get_user(user_id: int) -> User | None:
    with closing(_connect()) as conn:
        return _user(conn.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE id = ?", (user_id,)).fetchone())


def get_user_by_email(email: str) -> tuple[User | None, str | None]:
    with closing(_connect()) as conn:
        row = conn.execute(f"SELECT {_USER_COLUMNS}, password_hash FROM users WHERE email = ?", (email,)).fetchone()
    if row is None:
        return None, None
    return _user(row[:-1]), row[-1]


def update_user(user_id: int, **fields) -> None:
    bad = set(fields) - _PROFILE_FIELDS
    if bad:
        raise ValueError(f"campos no permitidos: {sorted(bad)}")
    if not fields:
        return
    assignments = ", ".join(f"{name} = ?" for name in fields)
    values = [int(v) if isinstance(v, bool) else v for v in fields.values()]
    with closing(_connect()) as conn, conn:
        conn.execute(f"UPDATE users SET {assignments} WHERE id = ?", [*values, user_id])


def list_users() -> list[User]:
    with closing(_connect()) as conn:
        return [_user(r) for r in conn.execute(f"SELECT {_USER_COLUMNS} FROM users ORDER BY id").fetchall()]


def create_session(user_id: int, token_digest: str) -> None:
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat()
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_now(),))
        conn.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                     (token_digest, user_id, _now(), expires))


def user_for_session(token_digest: str) -> User | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            f"SELECT {', '.join('u.' + c.strip() for c in _USER_COLUMNS.split(','))} FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires_at > ?",
            (token_digest, _now()),
        ).fetchone()
    return _user(row)


def delete_session(token_digest: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_digest,))


def delete_user_sessions(user_id: int) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def create_reset(user_id: int, code_hash: str, expires_at: str) -> None:
    """One live reset code per person: a new one replaces the previous."""
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM resets WHERE user_id = ?", (user_id,))
        conn.execute("INSERT INTO resets (code_hash, user_id, expires_at) VALUES (?, ?, ?)", (code_hash, user_id, expires_at))


def consume_reset(user_id: int, code_hash: str) -> bool:
    """True once, if the person's code matches and has not expired."""
    with closing(_connect()) as conn, conn:
        row = conn.execute("SELECT expires_at FROM resets WHERE user_id = ? AND code_hash = ?", (user_id, code_hash)).fetchone()
        if row is None:
            return False
        conn.execute("DELETE FROM resets WHERE user_id = ?", (user_id,))
        return row[0] > _now()


def create_invite(code: str, note: str | None, created_by: int) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT INTO invites (code, note, created_by, created_at) VALUES (?, ?, ?, ?)",
                     (code, (note or "").strip()[:80] or None, created_by, _now()))


def list_invites() -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT i.code, i.note, i.created_at, i.used_at, u.name, u.email FROM invites i "
            "LEFT JOIN users u ON u.id = i.used_by ORDER BY i.created_at DESC LIMIT 100"
        ).fetchall()
    return [{"code": r[0], "note": r[1], "created_at": r[2], "used_at": r[3], "used_by": r[4] or r[5]} for r in rows]


def delete_invite(code: str) -> bool:
    with closing(_connect()) as conn, conn:
        return conn.execute("DELETE FROM invites WHERE code = ? AND used_by IS NULL", (code.upper(),)).rowcount > 0


def set_weight(user_id: int, day: str, kg: float) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT OR REPLACE INTO weights (user_id, day, kg) VALUES (?, ?, ?)", (user_id, day, kg))


def latest_weight(user_id: int) -> float | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT kg FROM weights WHERE user_id = ? ORDER BY day DESC LIMIT 1", (user_id,)).fetchone()
    return row[0] if row else None


def bump_usage(user_id: int, day: str, limit: int) -> bool:
    """Count one photo analysis for the day; False (and no count) when the daily limit is used up."""
    with closing(_connect()) as conn:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT OR IGNORE INTO usage (user_id, day, analyses) VALUES (?, ?, 0)", (user_id, day))
        used = conn.execute("SELECT analyses FROM usage WHERE user_id = ? AND day = ?", (user_id, day)).fetchone()[0]
        if limit and used >= limit:
            conn.execute("ROLLBACK")
            return False
        conn.execute("UPDATE usage SET analyses = analyses + 1 WHERE user_id = ? AND day = ?", (user_id, day))
        conn.execute("COMMIT")
        return True


def entry_owner(entry_id: str) -> int | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT user_id FROM entry_meta WHERE entry_id = ?", (str(entry_id),)).fetchone()
    return row[0] if row else None


def plate_owner(key: str) -> int | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT user_id FROM plates WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def claim_entry(entry_id: str, user_id: int) -> None:
    """Record that an entry (already known to belong to this user's wger plan) is theirs."""
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT OR IGNORE INTO entry_meta (entry_id) VALUES (?)", (str(entry_id),))
        conn.execute("UPDATE entry_meta SET user_id = ? WHERE entry_id = ? AND user_id IS NULL", (user_id, str(entry_id)))


# ------------------------------------------------------------------ own foods and local diary entries
# wger's catalog is read-only through its API, so a food a person makes (or scans) lives here, and the
# entries that use it too. A custom food has ingredient id -<id> everywhere; its entries are "c<id>".

def create_custom_food(user_id: int, name: str, kcal: float, protein: float, carbs: float, fat: float,
                       barcode: str | None = None) -> int:
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO custom_foods (user_id, name, kcal, protein, carbs, fat, barcode, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, name.strip(), kcal, protein, carbs, fat, barcode or None, _now()))
        return cur.lastrowid


def _food(row) -> dict:
    return {"id": -row[0], "user_id": row[1], "name": row[2], "energy": row[3], "protein": row[4],
            "carbohydrates": row[5], "fat": row[6], "barcode": row[7], "source": "custom"}


_FOOD_COLUMNS = "id, user_id, name, kcal, protein, carbs, fat, barcode"


def get_custom_food(ingredient_id: int, user_id: int | None = None) -> dict | None:
    """By ingredient id (negative). With user_id, only if it is that person's."""
    with closing(_connect()) as conn:
        row = conn.execute(f"SELECT {_FOOD_COLUMNS} FROM custom_foods WHERE id = ?", (-int(ingredient_id),)).fetchone()
    if row is None or (user_id is not None and row[1] != user_id):
        return None
    return _food(row)


def custom_foods(user_id: int, term: str | None = None) -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(f"SELECT {_FOOD_COLUMNS} FROM custom_foods WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    foods = [_food(r) for r in rows]
    if term:
        words = term.lower().split()
        foods = [f for f in foods if any(w in f["name"].lower() for w in words)]
    return foods


def custom_food_by_barcode(user_id: int, code: str) -> dict | None:
    with closing(_connect()) as conn:
        row = conn.execute(f"SELECT {_FOOD_COLUMNS} FROM custom_foods WHERE user_id = ? AND barcode = ? ORDER BY id DESC",
                           (user_id, code)).fetchone()
    return _food(row) if row else None


def _utc_naive(when: datetime) -> str:
    return when.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def add_local_entry(user_id: int, ingredient_id: int, grams: float, when: datetime) -> str:
    with closing(_connect()) as conn, conn:
        cur = conn.execute("INSERT INTO local_entries (user_id, food_id, grams, at) VALUES (?,?,?,?)",
                           (user_id, -int(ingredient_id), grams, _utc_naive(when)))
        return f"c{cur.lastrowid}"


def local_entries(user_id: int, start: datetime, end: datetime) -> list[dict]:
    """The person's local entries in [start, end], shaped like wger's diary entries."""
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT id, food_id, grams, at FROM local_entries WHERE user_id = ? AND at >= ? AND at <= ?",
                            (user_id, _utc_naive(start), _utc_naive(end))).fetchall()
    return [{"id": f"c{r[0]}", "ingredient": -r[1], "amount": r[2], "datetime": r[3] + "+00:00"} for r in rows]


def _local_id(entry_id: str) -> int | None:
    text = str(entry_id)
    return int(text[1:]) if text.startswith("c") and text[1:].isdigit() else None


def is_local_entry(entry_id: str) -> bool:
    return _local_id(entry_id) is not None


def local_entry(entry_id: str) -> dict | None:
    lid = _local_id(entry_id)
    if lid is None:
        return None
    with closing(_connect()) as conn:
        row = conn.execute("SELECT id, user_id, food_id, grams, at FROM local_entries WHERE id = ?", (lid,)).fetchone()
    if row is None:
        return None
    return {"id": f"c{row[0]}", "user_id": row[1], "ingredient": -row[2], "amount": row[3], "datetime": row[4] + "+00:00"}


def update_local_entry(entry_id: str, grams: float | None = None, when: datetime | None = None) -> None:
    lid = _local_id(entry_id)
    with closing(_connect()) as conn, conn:
        if grams is not None:
            conn.execute("UPDATE local_entries SET grams = ? WHERE id = ?", (grams, lid))
        if when is not None:
            conn.execute("UPDATE local_entries SET at = ? WHERE id = ?", (_utc_naive(when), lid))


def delete_local_entry(entry_id: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM local_entries WHERE id = ?", (_local_id(entry_id),))


# ------------------------------------------------------------------ workouts (own log, per person)

def add_workout(user_id: int, day: str, kind: str, minutes: int, kcal: float, note: str | None) -> int:
    with closing(_connect()) as conn, conn:
        cur = conn.execute("INSERT INTO workouts (user_id, day, kind, minutes, kcal, note, created_at) VALUES (?,?,?,?,?,?,?)",
                           (user_id, day, kind, minutes, kcal, (note or "").strip() or None, _now()))
        return cur.lastrowid


def workouts_between(user_id: int, start_day: str, end_day: str) -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT id, day, kind, minutes, kcal, note FROM workouts WHERE user_id = ? AND day >= ? AND day <= ? ORDER BY id",
                            (user_id, start_day, end_day)).fetchall()
    return [{"id": r[0], "day": r[1], "kind": r[2], "minutes": r[3], "kcal": r[4], "note": r[5]} for r in rows]


def delete_workout(user_id: int, workout_id: int) -> bool:
    with closing(_connect()) as conn, conn:
        return conn.execute("DELETE FROM workouts WHERE id = ? AND user_id = ?", (workout_id, user_id)).rowcount > 0


def weights_since(user_id: int, since_day: str) -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT day, kg FROM weights WHERE user_id = ? AND day >= ? ORDER BY day", (user_id, since_day)).fetchall()
    return [{"day": r[0], "kg": r[1]} for r in rows]


def delete_weight(user_id: int, day: str) -> bool:
    with closing(_connect()) as conn, conn:
        return conn.execute("DELETE FROM weights WHERE user_id = ? AND day = ?", (user_id, day)).rowcount > 0


def photo_count(user_id: int) -> int:
    with closing(_connect()) as conn:
        return conn.execute("SELECT COUNT(*) FROM entry_meta WHERE user_id = ? AND plate_key IS NOT NULL", (user_id,)).fetchone()[0]
