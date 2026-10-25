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
CREATE TABLE IF NOT EXISTS avatars (user_id INTEGER PRIMARY KEY, data BLOB NOT NULL, version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS water_log (user_id INTEGER NOT NULL, day TEXT NOT NULL, ml INTEGER NOT NULL, PRIMARY KEY (user_id, day));
CREATE TABLE IF NOT EXISTS water_goals (user_id INTEGER PRIMARY KEY, ml INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS awards (
  user_id INTEGER NOT NULL, key TEXT NOT NULL, day TEXT NOT NULL, ref TEXT NOT NULL DEFAULT '', PRIMARY KEY (user_id, key, day, ref)
);
CREATE TABLE IF NOT EXISTS coin_ledger (
  user_id INTEGER NOT NULL, key TEXT NOT NULL, period TEXT NOT NULL, amount INTEGER NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, key, period)
);
CREATE TABLE IF NOT EXISTS equipped (user_id INTEGER NOT NULL, slot TEXT NOT NULL, item TEXT NOT NULL, PRIMARY KEY (user_id, slot));
CREATE TABLE IF NOT EXISTS push_subs (
  endpoint TEXT PRIMARY KEY, user_id INTEGER NOT NULL, p256dh TEXT NOT NULL, auth TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminder_prefs (user_id INTEGER PRIMARY KEY, prefs TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reminder_sent (user_id INTEGER NOT NULL, key TEXT NOT NULL, day TEXT NOT NULL, PRIMARY KEY (user_id, key, day));
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
        ("custom_foods", "fibre", "REAL"),  # optional: grams of fibre per 100 g
        ("workouts", "at", "TEXT"),  # local time (HH:MM) the workout was done
        ("users", "units", "TEXT"),  # JSON: how this person wants to SEE weight / height / liquids (data is always metric)
        ("users", "pace_lb", "REAL"),  # pounds per month the goal was chosen by (None = calories set by hand / old rule)
        # 0 = has not seen the one-time "what changed" welcome yet. Everyone who existed when this column appeared
        # starts at 0; accounts created afterwards are inserted with 1 (they go through the full first-use flow).
        ("users", "welcome_v2", "INTEGER NOT NULL DEFAULT 0"),
        ("entry_meta", "liquid", "INTEGER"),  # 1 = measured in millilitres (the model or the person said so)
        ("custom_foods", "liquid", "INTEGER"),
        # Block 14: how much the person moves (lifestyle level, optional steps, planned exercise as JSON), strength-training
        # experience, optional body fat, health flags (JSON), the calibration factor learnt from their own weight and food,
        # and whether they did the one-time review of their calories (0 for everyone who existed when this appeared).
        ("users", "lifestyle", "TEXT"),
        ("users", "steps", "INTEGER"),
        ("users", "training", "TEXT"),
        ("users", "lift_exp", "TEXT"),
        ("users", "body_fat", "REAL"),
        ("users", "health", "TEXT"),
        ("users", "tee_factor", "REAL"),
        ("users", "calc_done", "INTEGER NOT NULL DEFAULT 0"),
        ("users", "calib_next", "TEXT"),
        ("usage", "chats", "INTEGER NOT NULL DEFAULT 0"),  # messages to the interview / assistant today
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
            f"SELECT entry_id, note, crop IS NOT NULL, plate_key, box, liquid FROM entry_meta WHERE entry_id IN ({marks})",
            [str(i) for i in entry_ids],
        ).fetchall()
    return {
        row[0]: {"note": row[1] or None, "has_crop": bool(row[2]), "plate_key": row[3],
                 "box": json.loads(row[4]) if row[4] else None, "liquid": None if row[5] is None else bool(row[5])}
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


def set_liquid(entry_ids_by_flag: dict[str, bool], user_id: int | None = None) -> None:
    """Remember which entries are measured in millilitres (entry id -> True/False), when the model or the person said so."""
    with closing(_connect()) as conn, conn:
        for entry_id, liquid in entry_ids_by_flag.items():
            conn.execute("INSERT OR IGNORE INTO entry_meta (entry_id) VALUES (?)", (str(entry_id),))
            conn.execute("UPDATE entry_meta SET liquid = ?, user_id = COALESCE(user_id, ?) WHERE entry_id = ?",
                         (int(liquid), user_id, str(entry_id)))


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
    units: str | None = None
    pace_lb: float | None = None
    welcome_v2: bool = True
    lifestyle: str | None = None  # very_low | low | light | moderate | heavy: daily life WITHOUT planned exercise
    steps: int | None = None  # average steps of a normal day, if the person knows them
    training: str | None = None  # JSON [{kind, minutes, days}]
    lift_exp: str | None = None  # beginner | intermediate | advanced (strength training experience)
    body_fat: float | None = None
    health: str | None = None  # JSON flags: pregnancy, lactation, diabetes, kidney, professional, ed_risk
    tee_factor: float | None = None  # what their own weight and food taught us about their expenditure (1 = the formula)
    calc_done: bool = True
    calib_next: str | None = None  # day from which a new calibration suggestion may appear


_USER_COLUMNS = ("id, email, name, is_admin, plan_id, sex, birthdate, height_cm, activity, goal, target_weight_kg, "
                 "goal_kcal, goal_protein, goal_carbs, goal_fat, onboarded, created_at, units, pace_lb, welcome_v2, "
                 "lifestyle, steps, training, lift_exp, body_fat, health, tee_factor, calc_done, calib_next")
_COLUMN_LIST = [c.strip() for c in _USER_COLUMNS.split(",")]
_BOOL_COLUMNS = [_COLUMN_LIST.index(name) for name in ("is_admin", "onboarded", "welcome_v2", "calc_done")]
_PROFILE_FIELDS = {"name", "sex", "birthdate", "height_cm", "activity", "goal", "target_weight_kg", "goal_kcal",
                   "goal_protein", "goal_carbs", "goal_fat", "onboarded", "plan_id", "password_hash", "units", "pace_lb",
                   "welcome_v2", "lifestyle", "steps", "training", "lift_exp", "body_fat", "health", "tee_factor",
                   "calc_done", "calib_next"}


def _user(row) -> User | None:
    if row is None:
        return None
    values = list(row)
    for i in _BOOL_COLUMNS:
        values[i] = bool(values[i])
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
                "INSERT INTO users (email, name, password_hash, is_admin, created_at, welcome_v2, calc_done) VALUES (?, ?, ?, ?, ?, 1, 1)",
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


WATER_MAX_ML = 10000


def water_ml(user_id: int, day: str) -> int:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT ml FROM water_log WHERE user_id = ? AND day = ?", (user_id, day)).fetchone()
    return row[0] if row else 0


def add_water(user_id: int, day: str, delta_ml: int) -> int:
    """Adds (or removes) millilitres to a day and returns the new total. One statement, so two devices never overwrite each other."""
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT INTO water_log (user_id, day, ml) VALUES (?, ?, MIN(?, MAX(0, ?))) "
            "ON CONFLICT(user_id, day) DO UPDATE SET ml = MIN(?, MAX(0, ml + ?))",
            (user_id, day, WATER_MAX_ML, delta_ml, WATER_MAX_ML, delta_ml),
        )
        return conn.execute("SELECT ml FROM water_log WHERE user_id = ? AND day = ?", (user_id, day)).fetchone()[0]


def water_goal(user_id: int) -> int | None:
    """The goal the person set (None = automatic, from their weight)."""
    with closing(_connect()) as conn:
        row = conn.execute("SELECT ml FROM water_goals WHERE user_id = ?", (user_id,)).fetchone()
    return row[0] if row else None


def set_water_goal(user_id: int, ml: int | None) -> None:
    with closing(_connect()) as conn, conn:
        if ml is None:
            conn.execute("DELETE FROM water_goals WHERE user_id = ?", (user_id,))
        else:
            conn.execute("INSERT OR REPLACE INTO water_goals (user_id, ml) VALUES (?, ?)", (user_id, ml))


def water_range(user_id: int, start_day: str, end_day: str) -> dict[str, int]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT day, ml FROM water_log WHERE user_id = ? AND day >= ? AND day <= ?", (user_id, start_day, end_day)).fetchall()
    return {day: ml for day, ml in rows}


# ------------------------------------------------------------------ awards, coins and the shop
def record_awards(user_id: int, rows: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Saves (key, day, ref) awards; returns the ones that were new (already saved ones stay as they were)."""
    new = []
    with closing(_connect()) as conn, conn:
        for key, day, ref in rows:
            if conn.execute("INSERT OR IGNORE INTO awards (user_id, key, day, ref) VALUES (?,?,?,?)", (user_id, key, day, ref)).rowcount:
                new.append((key, day, ref))
    return new


def awards_summary(user_id: int) -> dict[str, dict]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT key, COUNT(*), MIN(day), MAX(day) FROM awards WHERE user_id = ? GROUP BY key", (user_id,)).fetchall()
    return {key: {"count": n, "first_day": first, "last_day": last} for key, n, first, last in rows}


def awards_on(user_id: int, day: str) -> list[tuple[str, str]]:
    """(key, ref) of the awards saved for a day (ref = the meal for meal awards)."""
    with closing(_connect()) as conn:
        return conn.execute("SELECT key, ref FROM awards WHERE user_id = ? AND day = ?", (user_id, day)).fetchall()


def coin_balance(user_id: int) -> int:
    with closing(_connect()) as conn:
        return conn.execute("SELECT COALESCE(SUM(amount), 0) FROM coin_ledger WHERE user_id = ?", (user_id,)).fetchone()[0]


def claimed_periods(user_id: int, keys: list[str], periods: list[str]) -> set[tuple[str, str]]:
    if not keys:
        return set()
    marks = ",".join("?" * len(keys))
    pmarks = ",".join("?" * len(periods))
    with closing(_connect()) as conn:
        rows = conn.execute(f"SELECT key, period FROM coin_ledger WHERE user_id = ? AND key IN ({marks}) AND period IN ({pmarks})",
                            [user_id, *keys, *periods]).fetchall()
    return {(k, p) for k, p in rows}


def add_coins(user_id: int, key: str, period: str, amount: int) -> bool:
    """One coin entry per (key, period): False when it was already there (a reward cannot be claimed twice)."""
    with closing(_connect()) as conn, conn:
        return bool(conn.execute("INSERT OR IGNORE INTO coin_ledger (user_id, key, period, amount, created_at) VALUES (?,?,?,?,?)",
                                 (user_id, key, period, amount, _now())).rowcount)


def owned_items(user_id: int) -> set[str]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT key FROM coin_ledger WHERE user_id = ? AND key LIKE 'shop:%'", (user_id,)).fetchall()
    return {k[5:] for (k,) in rows}


def buy_item(user_id: int, item: str, price: int) -> bool:
    """Spends coins on a shop item in one go: False when it was bought already or the coins are not enough."""
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            have = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM coin_ledger WHERE user_id = ?", (user_id,)).fetchone()[0]
            if have < price:
                conn.execute("ROLLBACK")
                return False
            ok = bool(conn.execute("INSERT OR IGNORE INTO coin_ledger (user_id, key, period, amount, created_at) VALUES (?,?,?,?,?)",
                                   (user_id, f"shop:{item}", "", -price, _now())).rowcount)
            conn.execute("COMMIT" if ok else "ROLLBACK")
            return ok
        except Exception:
            conn.execute("ROLLBACK")
            raise


def equipped_items(user_id: int) -> dict[str, str]:
    with closing(_connect()) as conn:
        return dict(conn.execute("SELECT slot, item FROM equipped WHERE user_id = ?", (user_id,)).fetchall())


def equip_item(user_id: int, slot: str, item: str | None) -> None:
    with closing(_connect()) as conn, conn:
        if item is None:
            conn.execute("DELETE FROM equipped WHERE user_id = ? AND slot = ?", (user_id, slot))
        else:
            conn.execute("INSERT OR REPLACE INTO equipped (user_id, slot, item) VALUES (?,?,?)", (user_id, slot, item))


def workouts_count(user_id: int) -> int:
    with closing(_connect()) as conn:
        return conn.execute("SELECT COUNT(*) FROM workouts WHERE user_id = ?", (user_id,)).fetchone()[0]


def import_water(user_id: int, days: dict[str, int]) -> None:
    """Water that only lived on one device: keeps the larger of what the server has and what the device had."""
    with closing(_connect()) as conn, conn:
        for day, ml in days.items():
            conn.execute(
                "INSERT INTO water_log (user_id, day, ml) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, day) DO UPDATE SET ml = MAX(ml, excluded.ml)",
                (user_id, day, min(WATER_MAX_ML, max(0, ml))),
            )


def set_weight(user_id: int, day: str, kg: float) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT OR REPLACE INTO weights (user_id, day, kg) VALUES (?, ?, ?)", (user_id, day, kg))


def latest_weight(user_id: int) -> float | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT kg FROM weights WHERE user_id = ? ORDER BY day DESC LIMIT 1", (user_id,)).fetchone()
    return row[0] if row else None


def bump_usage(user_id: int, day: str, limit: int, kind: str = "analyses") -> bool:
    """Count one use of the AI for the day (`analyses`: photos, voice, ideas; `chats`: interview and assistant messages);
    False (and no count) when that day's limit is used up."""
    if kind not in ("analyses", "chats"):
        raise ValueError(kind)
    with closing(_connect()) as conn:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT OR IGNORE INTO usage (user_id, day, analyses) VALUES (?, ?, 0)", (user_id, day))
        used = conn.execute(f"SELECT {kind} FROM usage WHERE user_id = ? AND day = ?", (user_id, day)).fetchone()[0]
        if limit and used >= limit:
            conn.execute("ROLLBACK")
            return False
        conn.execute(f"UPDATE usage SET {kind} = {kind} + 1 WHERE user_id = ? AND day = ?", (user_id, day))
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
                       barcode: str | None = None, fibre: float | None = None, liquid: bool | None = None) -> int:
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO custom_foods (user_id, name, kcal, protein, carbs, fat, barcode, created_at, fibre, liquid) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (user_id, name.strip(), kcal, protein, carbs, fat, barcode or None, _now(), fibre,
             None if liquid is None else int(liquid)))
        return cur.lastrowid


def _food(row) -> dict:
    return {"id": -row[0], "user_id": row[1], "name": row[2], "energy": row[3], "protein": row[4],
            "carbohydrates": row[5], "fat": row[6], "barcode": row[7], "source": "custom", "fibres": row[8],
            "liquid": None if row[9] is None else bool(row[9])}


_FOOD_COLUMNS = "id, user_id, name, kcal, protein, carbs, fat, barcode, fibre, liquid"


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

def add_workout(user_id: int, day: str, kind: str, minutes: int, kcal: float, note: str | None, at: str | None = None) -> int:
    with closing(_connect()) as conn, conn:
        cur = conn.execute("INSERT INTO workouts (user_id, day, kind, minutes, kcal, note, created_at, at) VALUES (?,?,?,?,?,?,?,?)",
                           (user_id, day, kind, minutes, kcal, (note or "").strip() or None, _now(), at))
        return cur.lastrowid


def update_workout(user_id: int, workout_id: int, kind: str, minutes: int, kcal: float, note: str | None, at: str | None) -> bool:
    with closing(_connect()) as conn, conn:
        return conn.execute("UPDATE workouts SET kind = ?, minutes = ?, kcal = ?, note = ?, at = ? WHERE id = ? AND user_id = ?",
                            (kind, minutes, kcal, (note or "").strip() or None, at, workout_id, user_id)).rowcount > 0


def workouts_between(user_id: int, start_day: str, end_day: str) -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT id, day, kind, minutes, kcal, note, at FROM workouts WHERE user_id = ? AND day >= ? AND day <= ? ORDER BY id",
                            (user_id, start_day, end_day)).fetchall()
    return [{"id": r[0], "day": r[1], "kind": r[2], "minutes": r[3], "kcal": r[4], "note": r[5], "at": r[6]} for r in rows]


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


# ------------------------------------------------------------------ push subscriptions and reminders

def get_kv(key: str) -> str | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_kv_if_absent(key: str, value: str) -> str:
    """Store value unless a (concurrent) request already did; returns what is stored."""
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT OR IGNORE INTO kv (key, value) VALUES (?, ?)", (key, value))
        return conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()[0]


def save_subscription(user_id: int, endpoint: str, p256dh: str, auth: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT OR REPLACE INTO push_subs (endpoint, user_id, p256dh, auth, created_at) VALUES (?,?,?,?,?)",
                     (endpoint, user_id, p256dh, auth, _now()))


def delete_subscription(endpoint: str, user_id: int | None = None) -> None:
    with closing(_connect()) as conn, conn:
        if user_id is None:
            conn.execute("DELETE FROM push_subs WHERE endpoint = ?", (endpoint,))
        else:
            conn.execute("DELETE FROM push_subs WHERE endpoint = ? AND user_id = ?", (endpoint, user_id))


def subscriptions(user_id: int) -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT endpoint, p256dh, auth FROM push_subs WHERE user_id = ?", (user_id,)).fetchall()
    return [{"endpoint": r[0], "keys": {"p256dh": r[1], "auth": r[2]}} for r in rows]


def users_with_subscriptions() -> list[int]:
    with closing(_connect()) as conn:
        return [r[0] for r in conn.execute("SELECT DISTINCT user_id FROM push_subs")]


def get_reminder_prefs(user_id: int) -> dict | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT prefs FROM reminder_prefs WHERE user_id = ?", (user_id,)).fetchone()
    return json.loads(row[0]) if row else None


def set_reminder_prefs(user_id: int, prefs: dict) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT OR REPLACE INTO reminder_prefs (user_id, prefs) VALUES (?, ?)", (user_id, json.dumps(prefs)))


def claim_reminder(user_id: int, key: str, day: str) -> bool:
    """True for the first caller only: a reminder goes out once per person, key and day (even with several workers)."""
    with closing(_connect()) as conn, conn:
        return conn.execute("INSERT OR IGNORE INTO reminder_sent (user_id, key, day) VALUES (?,?,?)", (user_id, key, day)).rowcount == 1


def prune_reminders(before_day: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM reminder_sent WHERE day < ?", (before_day,))


# ------------------------------------------------------------------ profile picture

def set_avatar(user_id: int, data: bytes) -> int:
    version = int(datetime.now(timezone.utc).timestamp())
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT OR REPLACE INTO avatars (user_id, data, version) VALUES (?,?,?)", (user_id, data, version))
    return version


def get_avatar(user_id: int) -> tuple[bytes, int] | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT data, version FROM avatars WHERE user_id = ?", (user_id,)).fetchone()
    return (row[0], row[1]) if row else None


def avatar_version(user_id: int) -> int | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT version FROM avatars WHERE user_id = ?", (user_id,)).fetchone()
    return row[0] if row else None


def delete_avatar(user_id: int) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM avatars WHERE user_id = ?", (user_id,))
