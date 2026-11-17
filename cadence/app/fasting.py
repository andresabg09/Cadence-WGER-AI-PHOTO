"""Intermittent fasting (Block 17, 17 nov 2026): plans, the honest body stages, safety and the fast log.

What cadence promises and what it does not (see CLAUDE.md, "AYUNO"):
- Fasting orders WHEN a person eats. In the trials, an eating window did not lose more weight than eating less without one
  (Liu, NEJM 2022; Lowe, JAMA Intern Med 2020), so the calorie goal never changes because of a fast.
- Plans go from 12:12 to 18:6 (or 12 to 18 h of one's own). Nothing rewards fasting longer than the plan.
- The stages are approximate hours after the last meal, worded as such. Autophagy has no hour here: in people nobody knows
  when it starts (the numbers that circulate come from animal studies).
- Not available for minors, a positive eating-disorder screening, pregnancy or breastfeeding, diabetes (insulin and
  sulfonylureas cause lows when fasting; SGLT2 inhibitors, ketoacidosis), a BMI under 18.5, or anyone who said one of those
  applies to them. The reasons come from the health data cadence already keeps.
"""

import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import accounts, auth, nutrition, store
from .meals import local_now, local_tz

logger = logging.getLogger("cadence.fasting")
router = APIRouter()

MIN_HOURS, MAX_HOURS = 12, 18
PLANS = [(12, "Para empezar"), (13, "Para empezar"), (14, "Para empezar"), (16, "Habitual"), (18, "Habitual")]
DEFAULT_HOURS, DEFAULT_START = 14, "20:00"
FORGOT_AFTER_H = 24  # an open fast this long is most likely one somebody forgot to end
MAX_RECORD_H = 48  # a fast written by hand longer than this is a typing mistake
GRACE_MIN = 5  # ending 5 minutes early still completes the plan

# key, from hour, title, what happens (plain words, approximate), Phosphor icon name
STAGES = [
    ("digest", 0, "Digieres lo que comiste",
     "Lo que comiste pasa a la sangre como glucosa y el azúcar sube. El cuerpo libera insulina para llevar esa energía a las "
     "células y guardar lo que sobra en el hígado y los músculos.", "fork-knife"),
    ("normal", 3, "El azúcar vuelve a lo normal",
     "La insulina baja y el azúcar en la sangre regresa a su nivel de siempre. Tu cuerpo sigue usando la energía de tu última comida.",
     "drop"),
    ("reserves", 8, "El hígado usa sus reservas",
     "Para que el azúcar no baje de más, una hormona llamada glucagón le pide al hígado que suelte lo que tenía guardado "
     "(glucógeno). Así tienes energía estable aunque no comas.", "battery-medium"),
    ("fat", 12, "Empiezas a usar más grasa",
     "Cuando las reservas del hígado bajan, el cuerpo usa cada vez más grasa como energía. En general este cambio ocurre entre "
     "las 12 y las 36 horas, según lo que comiste y cuánto te moviste.", "fire"),
    ("ketones", 16, "Las cetonas suben poco a poco",
     "Al usar grasa, el hígado produce cetonas, otra fuente de energía para el cerebro y los músculos. En un ayuno de 16 a 18 "
     "horas suben poco; no hace falta más para que tu plan funcione.", "lightning"),
]
SOURCES = [
    "Liu et al., N Engl J Med 2022 (ayuno con horario frente a solo comer menos, 12 meses)",
    "Lowe et al., JAMA Intern Med 2020 (16:8, sin diferencia frente a comer a cualquier hora)",
    "Anton et al., Obesity 2018 (el cambio a usar grasa, entre 12 y 36 h)",
    "Bagherniya et al., Ageing Res Rev 2018 (autofagia: datos sobre todo en animales)",
]
BLOCK_TEXT = {
    "minor": "Eres menor de edad: tu cuerpo todavía está creciendo y necesita comer con regularidad.",
    "ed": "Por cómo respondiste las preguntas de cuidado con la comida, pasar horas sin comer podría hacerte daño.",
    "pregnancy": "Durante el embarazo o la lactancia tu cuerpo necesita comer con regularidad.",
    "diabetes": "Con diabetes, ayunar puede bajarte el azúcar de más o causar otros problemas con tus medicinas. "
                "Si tu médico te indicó un horario, síguelo con él.",
    "underweight": "Tu peso ya es bajo para tu estatura: ahora lo importante es comer bien, no ayunar.",
    "self": "Nos dijiste que alguna de las situaciones de cuidado aplica para ti.",
}


def plan_label(hours: int) -> str:
    return f"{hours}:{24 - hours}"


def clean_hours(value) -> int:
    try:
        hours = int(value)
    except (TypeError, ValueError):
        return DEFAULT_HOURS
    return hours if MIN_HOURS <= hours <= MAX_HOURS else DEFAULT_HOURS


def stage_index(hours: float) -> int:
    index = 0
    for i, stage in enumerate(STAGES):
        if hours >= stage[1]:
            index = i
    return index


def stages_out() -> list[dict]:
    return [{"key": k, "from_h": h, "title": t, "body": b, "icon": i} for k, h, t, b, i in STAGES]


def blocked_reason(user: store.User, today: date | None = None, plan: dict | None = None) -> str | None:
    """Why this person must not be offered fasting (None = it can be). Code, not a setting: nothing can override it."""
    health = accounts.health_of(user)
    today = today or local_now().date()
    if user.birthdate:
        try:
            if nutrition.age_on(date.fromisoformat(user.birthdate), today) < 18:
                return "minor"
        except ValueError:
            pass
    if health.get("ed_risk"):
        return "ed"
    if health.get("pregnancy") or health.get("lactation"):
        return "pregnancy"
    if health.get("diabetes"):
        return "diabetes"
    weight = store.latest_weight(user.id)
    if weight and user.height_cm and weight / ((user.height_cm / 100) ** 2) < 18.5:
        return "underweight"
    if (plan or store.fasting_plan(user.id) or {}).get("self_excluded"):
        return "self"
    return None


def parse_when(raw: str | None, now: datetime) -> datetime:
    """A time the person gave (naive = their local clock). Missing -> now; a time in the future is not allowed."""
    if not raw:
        return now
    try:
        when = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, "Hora no válida")
    when = when.replace(tzinfo=local_tz()) if when.tzinfo is None else when.astimezone(local_tz())
    if when > now + timedelta(minutes=1):
        raise HTTPException(422, "Esa hora todavía no llega")
    return when


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(local_tz())


def fast_out(row: dict, now: datetime) -> dict:
    start = _dt(row["started_at"])
    end = _dt(row["ended_at"]) if row.get("ended_at") else None
    hours = ((end or now) - start).total_seconds() / 3600
    planned = float(row["planned_h"])
    return {
        "id": row["id"], "started_at": start.isoformat(), "ended_at": end.isoformat() if end else None,
        "planned_h": planned, "hours": round(hours, 2), "active": end is None,
        "ends_at": (start + timedelta(hours=planned)).isoformat(),
        "complete": end is not None and hours * 60 >= planned * 60 - GRACE_MIN,
        "stage": stage_index(hours),
        "overdue": end is None and hours >= FORGOT_AFTER_H,
    }


def next_start(plan: dict, now: datetime) -> datetime:
    hh, mm = (int(x) for x in plan["start"].split(":"))
    at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return at if at > now else at + timedelta(days=1)


def week_stats(fasts: list[dict], today: date) -> dict:
    """Completed fasts in the last 7 days (a fast counts on the day it ended)."""
    since = today - timedelta(days=6)
    done_days = {date.fromisoformat(f["ended_at"][:10]) for f in fasts if f["complete"] and f["ended_at"]}
    return {"done": sum(1 for d in done_days if since <= d <= today), "days": 7}


def plan_out(plan: dict | None) -> dict:
    plan = plan or {}
    hours = clean_hours(plan.get("hours"))
    return {"hours": hours, "eat_hours": 24 - hours, "label": plan_label(hours), "start": plan.get("start") or DEFAULT_START,
            "chosen": bool(plan.get("hours")), "intro_done": bool(plan.get("intro_done")), "self_excluded": bool(plan.get("self_excluded"))}


def state_for(user: store.User, now: datetime | None = None) -> dict:
    now = now or local_now()
    raw_plan = store.fasting_plan(user.id)
    plan = plan_out(raw_plan)
    reason = blocked_reason(user, now.date(), raw_plan)
    rows = store.fasts_recent(user.id, (now - timedelta(days=30)).isoformat())
    fasts = [fast_out(r, now) for r in rows]
    active = next((f for f in fasts if f["active"]), None)
    return {
        "blocked": reason, "blocked_text": BLOCK_TEXT.get(reason) if reason else None,
        "plan": plan, "plans": [{"hours": h, "label": plan_label(h), "group": g} for h, g in PLANS],
        "range": [MIN_HOURS, MAX_HOURS], "stages": stages_out(), "sources": SOURCES,
        "active": active, "next_start": None if active else next_start(plan, now).isoformat(),
        "history": [f for f in fasts if not f["active"]][:14], "week": week_stats(fasts, now.date()),
        "now": now.isoformat(),
    }


def due_reminders(state: dict, prefs: dict, now: datetime) -> list[tuple[str, str, str]]:
    """Fasting reminders due now: (dedupe key, title, body). Pure: the caller claims and sends."""
    out = []
    if state["blocked"] or not (prefs or {}).get("on"):
        return out
    window = timedelta(minutes=30)
    active = state["active"]
    if active:
        ends = datetime.fromisoformat(active["ends_at"])
        if ends <= now < ends + window:
            out.append((f"fast_end:{active['id']}", "Completaste tu ayuno",
                        f"Llegaste a tus {plan_label(int(active['planned_h']))}. Cuando comas, termínalo en cadence."))
        if prefs.get("half"):
            half = datetime.fromisoformat(active["started_at"]) + timedelta(hours=active["planned_h"] / 2)
            if half <= now < half + window:
                out.append((f"fast_half:{active['id']}", "Vas a la mitad de tu ayuno", "Bebe agua, café o té sin azúcar. Si te sientes mal, come."))
    elif state["plan"]["chosen"]:
        hh, mm = (int(x) for x in state["plan"]["start"].split(":"))
        start = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if start <= now < start + window:
            out.append(("fast_start", "Hora de empezar tu ayuno", f"Tu plan {state['plan']['label']} empieza ahora. Tócalo para iniciarlo."))
    return out


# ------------------------------------------------------------------ API

class PlanIn(BaseModel):
    hours: int = Field(ge=MIN_HOURS, le=MAX_HOURS)
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class IntroIn(BaseModel):
    none_apply: bool  # True = "Ninguna me aplica"; False = "Alguna me aplica" (fasting is then not offered)


class WhenIn(BaseModel):
    at: str | None = None


class FastIn(BaseModel):
    start: str | None = None
    end: str | None = None


def _require_allowed(user: store.User) -> None:
    reason = blocked_reason(user)
    if reason:
        raise HTTPException(403, BLOCK_TEXT[reason])


def _check_span(start: datetime, end: datetime | None, user_id: int, skip_id: int | None = None) -> None:
    if end is not None:
        if end <= start:
            raise HTTPException(422, "El fin tiene que ser después del inicio")
        if (end - start) > timedelta(hours=MAX_RECORD_H):
            raise HTTPException(422, f"Un ayuno de más de {MAX_RECORD_H} horas no se puede anotar: revisa las horas")
    if store.fast_overlaps(user_id, start.isoformat(), end.isoformat() if end else None, skip_id):
        raise HTTPException(409, "Ese horario se cruza con otro ayuno tuyo")


@router.get("/api/fasting")
def get_fasting(user: store.User = Depends(auth.current_user)):
    return state_for(user)


@router.put("/api/fasting/plan")
def put_plan(body: PlanIn, user: store.User = Depends(auth.current_user)):
    store.set_fasting_plan(user.id, hours=body.hours, start=body.start)
    return state_for(user)


@router.post("/api/fasting/intro")
def post_intro(body: IntroIn, user: store.User = Depends(auth.current_user)):
    store.set_fasting_plan(user.id, intro_done=1, self_excluded=0 if body.none_apply else 1)
    return state_for(user)


@router.post("/api/fasting/start")
def start_fast(body: WhenIn, user: store.User = Depends(auth.current_user)):
    _require_allowed(user)
    now = local_now()
    if store.fast_active(user.id):
        raise HTTPException(409, "Ya tienes un ayuno en curso")
    start = parse_when(body.at, now)
    if now - start > timedelta(hours=MAX_RECORD_H):
        raise HTTPException(422, "Ese inicio es de hace demasiado tiempo")
    _check_span(start, None, user.id)
    plan = plan_out(store.fasting_plan(user.id))
    store.fast_start(user.id, start.isoformat(), plan["hours"])
    return state_for(user)


@router.post("/api/fasting/end")
def end_fast(body: WhenIn, user: store.User = Depends(auth.current_user)):
    now = local_now()
    active = store.fast_active(user.id)
    if not active:
        raise HTTPException(409, "No tienes un ayuno en curso")
    end = parse_when(body.at, now)
    _check_span(_dt(active["started_at"]), end, user.id, skip_id=active["id"])
    store.fast_update(user.id, active["id"], ended_at=end.isoformat())
    state = state_for(user)
    state["ended"] = fast_out(store.fast_get(user.id, active["id"]), now)
    return state


@router.post("/api/fasting/past")
def add_past(body: FastIn, user: store.User = Depends(auth.current_user)):
    _require_allowed(user)
    now = local_now()
    if not body.start or not body.end:
        raise HTTPException(422, "Falta el inicio o el fin")
    start, end = parse_when(body.start, now), parse_when(body.end, now)
    _check_span(start, end, user.id)
    plan = plan_out(store.fasting_plan(user.id))
    store.fast_add(user.id, start.isoformat(), end.isoformat(), plan["hours"])
    return state_for(user)


@router.patch("/api/fasting/{fast_id}")
def edit_fast(fast_id: int, body: FastIn, user: store.User = Depends(auth.current_user)):
    row = store.fast_get(user.id, fast_id)
    if not row:
        raise HTTPException(404, "Ayuno no encontrado")
    now = local_now()
    start = parse_when(body.start, now) if body.start else _dt(row["started_at"])
    end = parse_when(body.end, now) if body.end else (_dt(row["ended_at"]) if row.get("ended_at") else None)
    _check_span(start, end, user.id, skip_id=fast_id)
    store.fast_update(user.id, fast_id, started_at=start.isoformat(), ended_at=end.isoformat() if end else None)
    return state_for(user)


@router.delete("/api/fasting/{fast_id}")
def delete_fast(fast_id: int, user: store.User = Depends(auth.current_user)):
    if not store.fast_delete(user.id, fast_id):
        raise HTTPException(404, "Ayuno no encontrado")
    return state_for(user)
