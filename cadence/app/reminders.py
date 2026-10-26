"""Reminders: preferences, push subscriptions and the minute-by-minute scheduler.

A reminder is due inside a 30-minute window after its time (a restart must not replay the morning at night),
once per person and day (`claim_reminder`). Meal reminders are skipped when that meal is already logged.
"""

import logging
import re
import threading
import time as clock
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth, store, webpush
from .config import settings
from .meals import entry_date, local_now, meal_key_for_entry

logger = logging.getLogger("cadence.reminders")
router = APIRouter()

WINDOW_MIN = 30
MEAL_TEXT = {
    "desayuno": ("Hora del desayuno", "Toma una foto de tu desayuno y cadence lo registra."),
    "almuerzo": ("Hora del almuerzo", "¿Ya almorzaste? Registra tu plato con una foto."),
    "cena": ("Hora de la cena", "Cierra el día: registra tu cena con una foto."),
}
DEFAULT_PREFS = {
    "water": {"on": False, "every_h": 2, "from": "08:00", "to": "22:00"},
    "meals": {"desayuno": {"on": False, "time": "08:00"}, "almuerzo": {"on": False, "time": "12:30"}, "cena": {"on": False, "time": "19:30"}},
    "weekly": {"on": False, "time": "09:00"},  # Sundays
}
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


@dataclass(frozen=True)
class Reminder:
    key: str  # dedupe key for the day
    title: str
    body: str
    url: str
    meal: str | None = None


def _at(text: str) -> time:
    return time(int(text[:2]), int(text[3:5]))


def clean_prefs(raw: dict | None) -> dict:
    """The stored preferences merged over the defaults, with every value validated."""
    raw = raw or {}
    prefs = {"water": dict(DEFAULT_PREFS["water"]), "meals": {k: dict(v) for k, v in DEFAULT_PREFS["meals"].items()},
             "weekly": dict(DEFAULT_PREFS["weekly"])}

    def hhmm(value, fallback):
        return value if isinstance(value, str) and _HHMM.match(value) else fallback

    water = raw.get("water") or {}
    prefs["water"]["on"] = bool(water.get("on"))
    prefs["water"]["every_h"] = water.get("every_h") if water.get("every_h") in (1, 2, 3, 4) else 2
    prefs["water"]["from"] = hhmm(water.get("from"), "08:00")
    prefs["water"]["to"] = hhmm(water.get("to"), "22:00")
    for meal, default in DEFAULT_PREFS["meals"].items():
        item = (raw.get("meals") or {}).get(meal) or {}
        prefs["meals"][meal] = {"on": bool(item.get("on")), "time": hhmm(item.get("time"), default["time"])}
    weekly = raw.get("weekly") or {}
    prefs["weekly"] = {"on": bool(weekly.get("on")), "time": hhmm(weekly.get("time"), "09:00")}
    return prefs


def _in_window(now: datetime, at: time) -> bool:
    start = datetime.combine(now.date(), at, tzinfo=now.tzinfo)
    return start <= now < start + timedelta(minutes=WINDOW_MIN)


def due_reminders(prefs: dict, now: datetime) -> list[Reminder]:
    """What should be sent right now (pure: no I/O, no memory of what was already sent)."""
    prefs = clean_prefs(prefs)
    due: list[Reminder] = []
    water = prefs["water"]
    if water["on"]:
        slot = datetime.combine(now.date(), _at(water["from"]), tzinfo=now.tzinfo)
        last = datetime.combine(now.date(), _at(water["to"]), tzinfo=now.tzinfo)
        while slot <= last:
            if slot <= now < slot + timedelta(minutes=WINDOW_MIN):
                due.append(Reminder(f"water:{slot:%H%M}", "Hora de tomar agua", "Un vaso ahora te acerca a tu meta de hoy.", "index.html"))
            slot += timedelta(hours=water["every_h"])
    for meal, item in prefs["meals"].items():
        if item["on"] and _in_window(now, _at(item["time"])):
            title, body = MEAL_TEXT[meal]
            due.append(Reminder(f"meal:{meal}", title, body, f"scan.html?meal={meal}", meal))
    weekly = prefs["weekly"]
    if weekly["on"] and now.weekday() == 6 and _in_window(now, _at(weekly["time"])):
        due.append(Reminder("weekly", "Tu resumen semanal", "", "progress.html"))
    return due


# ------------------------------------------------------------------ keys and sending

_keys_lock = threading.Lock()


def vapid_keys() -> tuple[str, str]:
    """(private, public). Generated once and kept in cadence's own store: nothing to configure."""
    with _keys_lock:
        private, public = store.get_kv("vapid_private"), store.get_kv("vapid_public")
        if not private or not public:
            fresh_private, fresh_public = webpush.generate_vapid_keys()
            private = store.set_kv_if_absent("vapid_private", fresh_private)
            public = store.set_kv_if_absent("vapid_public", fresh_public)
        return private, public


def push_to_user(user: store.User, message: dict) -> int:
    """Send to every device of the person; subscriptions the push service no longer knows are dropped."""
    private, public = vapid_keys()
    subject = f"mailto:{settings.admin_email or user.email}"
    sent = 0
    for sub in store.subscriptions(user.id):
        try:
            webpush.send(sub, message, private, public, subject)
            sent += 1
        except webpush.Gone:
            store.delete_subscription(sub["endpoint"])
        except Exception:  # noqa: BLE001 - one bad device must not stop the others
            logger.exception("no se pudo enviar el aviso a %s", sub["endpoint"][:60])
    return sent


def _meal_logged(user: store.User, meal: str, now: datetime) -> bool:
    """Has the person already logged this meal today? (Unknown -> False: better one reminder too many.)"""
    from .main import get_wger_client, plan_for, user_entries  # late: main imports this module

    wger = get_wger_client()
    try:
        plan_id = plan_for(wger, user, create=False)
        start = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo)
        end = datetime.combine(now.date(), time.max, tzinfo=now.tzinfo)
        return any(meal_key_for_entry(e) == meal for e in user_entries(wger, user, plan_id, start, end))
    except Exception:  # noqa: BLE001
        logger.exception("no se pudo comprobar la comida de hoy")
        return False
    finally:
        wger.close()


def _weekly_body(user: store.User, now: datetime) -> str:
    from .main import get_wger_client, ingredient_info, plan_for, user_entries
    from .progress import day_totals

    wger = get_wger_client()
    try:
        plan_id = plan_for(wger, user, create=False)
        start = datetime.combine(now.date() - timedelta(days=6), time.min, tzinfo=now.tzinfo)
        entries = user_entries(wger, user, plan_id, start, datetime.combine(now.date(), time.max, tzinfo=now.tzinfo))
        totals = day_totals(entries, lambda i: ingredient_info(wger, user, i))
    finally:
        wger.close()
    if not totals:
        return "Esta semana no registraste comidas. Mañana es un buen día para retomar."
    avg = round(sum(t["kcal"] for t in totals.values()) / len(totals))
    goal = round(user.goal_kcal or settings.fallback_goal_kcal)
    return f"Registraste {len(totals)} de 7 días, con un promedio de {avg} kcal (tu meta: {goal})."


def run_once(now: datetime | None = None) -> int:
    """One scheduler pass; returns how many notifications were sent."""
    now = now or local_now()
    day = now.date().isoformat()
    sent = 0
    for user_id in store.users_with_subscriptions():
        user = store.get_user(user_id)
        prefs = store.get_reminder_prefs(user_id)
        if user is None or prefs is None:
            continue
        for reminder in due_reminders(prefs, now):
            if reminder.meal and _meal_logged(user, reminder.meal, now):
                continue
            if not store.claim_reminder(user_id, reminder.key, day):
                continue
            body = reminder.body
            if reminder.key == "weekly":
                try:
                    body = _weekly_body(user, now)
                except Exception:  # noqa: BLE001
                    logger.exception("no se pudo armar el resumen semanal")
                    continue
            sent += push_to_user(user, {"title": reminder.title, "body": body, "url": reminder.url, "tag": reminder.key})
    store.prune_reminders((now.date() - timedelta(days=3)).isoformat())
    return sent


def start_scheduler() -> None:
    def loop():
        while True:
            clock.sleep(60 - clock.time() % 60)  # wake at the top of each minute
            try:
                run_once()
            except Exception:  # noqa: BLE001 - the loop must survive anything
                logger.exception("fallo el programador de recordatorios")

    threading.Thread(target=loop, name="reminders", daemon=True).start()


# ------------------------------------------------------------------ API

class SubscriptionIn(BaseModel):
    endpoint: str
    keys: dict[str, str]


@router.get("/api/push/key")
def push_key(_: store.User = Depends(auth.current_user)):
    return {"public_key": vapid_keys()[1]}


@router.post("/api/push/subscribe")
def subscribe(body: SubscriptionIn, user: store.User = Depends(auth.current_user)):
    if not body.endpoint.startswith("https://") or not body.keys.get("p256dh") or not body.keys.get("auth"):
        raise HTTPException(422, "Suscripción inválida")
    store.save_subscription(user.id, body.endpoint, body.keys["p256dh"], body.keys["auth"])
    return {"devices": len(store.subscriptions(user.id))}


@router.post("/api/push/unsubscribe")
def unsubscribe(body: SubscriptionIn, user: store.User = Depends(auth.current_user)):
    store.delete_subscription(body.endpoint, user.id)
    return {"devices": len(store.subscriptions(user.id))}


@router.post("/api/push/test")
def push_test(user: store.User = Depends(auth.current_user)):
    if not store.subscriptions(user.id):
        raise HTTPException(409, "Este dispositivo aún no tiene los avisos activados")
    sent = push_to_user(user, {"title": "cadence", "body": "¡Los avisos funcionan en este dispositivo!", "url": "index.html", "tag": "test"})
    if sent == 0:
        raise HTTPException(502, "No se pudo entregar el aviso. Activa los avisos de nuevo en este dispositivo.")
    return {"sent": sent}


@router.get("/api/reminders")
def get_reminders(user: store.User = Depends(auth.current_user)):
    return {"prefs": clean_prefs(store.get_reminder_prefs(user.id)), "devices": len(store.subscriptions(user.id))}


@router.put("/api/reminders")
def put_reminders(body: dict, user: store.User = Depends(auth.current_user)):
    prefs = clean_prefs(body)
    store.set_reminder_prefs(user.id, prefs)
    return {"prefs": prefs, "devices": len(store.subscriptions(user.id))}
