"""Fasting (Block 17): plans, honest stages, safety blocks, each person's own log, editing the past and the reminders."""

import json
from datetime import datetime, timedelta

import pytest

from app import fasting, reminders, store, webpush
from app.meals import local_now
from tests.test_foods import two_people, wger  # noqa: F401 - fixture
from tests.test_reminders import SUB

pytestmark = pytest.mark.anonymous


def iso(dt):
    return dt.replace(second=0, microsecond=0).isoformat()


def me_id(http):
    return http.get("/api/auth/me").json()["id"]


def test_stages_plans_and_labels_are_what_was_agreed():
    assert [h for h, _ in fasting.PLANS] == [12, 13, 14, 16, 18]
    assert fasting.plan_label(16) == "16:8" and fasting.clean_hours(20) == fasting.DEFAULT_HOURS and fasting.clean_hours(13) == 13
    assert [s[1] for s in fasting.STAGES] == [0, 3, 8, 12, 16]
    assert fasting.stage_index(0.5) == 0 and fasting.stage_index(10) == 2 and fasting.stage_index(17) == 4
    text = json.dumps(fasting.stages_out(), ensure_ascii=False).lower()
    assert "autofagia" not in text and "neurona" not in text  # no promises the evidence does not back


def test_plan_start_end_and_history(wger):
    admin, _ = two_people()
    state = admin.get("/api/fasting").json()
    assert state["blocked"] is None and state["active"] is None and state["plan"]["chosen"] is False
    assert admin.put("/api/fasting/plan", json={"hours": 20, "start": "20:00"}).status_code == 422  # never beyond 18 h
    state = admin.put("/api/fasting/plan", json={"hours": 16, "start": "20:00"}).json()
    assert state["plan"]["label"] == "16:8" and state["plan"]["chosen"]

    start = local_now() - timedelta(hours=10)
    state = admin.post("/api/fasting/start", json={"at": iso(start)}).json()
    assert state["active"]["planned_h"] == 16 and state["active"]["stage"] == 2 and state["next_start"] is None
    assert admin.post("/api/fasting/start", json={}).status_code == 409  # one open fast at a time
    future = local_now() + timedelta(hours=2)
    assert admin.post("/api/fasting/end", json={"at": iso(future)}).status_code == 422  # never in the future

    state = admin.post("/api/fasting/end", json={}).json()
    assert state["active"] is None and state["ended"]["complete"] is False  # ending early is fine, it just is not "complete"
    assert state["history"][0]["hours"] >= 9.9

    past_start = local_now() - timedelta(days=2, hours=18)
    state = admin.post("/api/fasting/past", json={"start": iso(past_start), "end": iso(past_start + timedelta(hours=16))}).json()
    assert any(f["complete"] for f in state["history"]) and state["week"]["done"] == 1
    overlap = admin.post("/api/fasting/past", json={"start": iso(past_start + timedelta(hours=2)), "end": iso(past_start + timedelta(hours=5))})
    assert overlap.status_code == 409
    too_long = admin.post("/api/fasting/past", json={"start": iso(local_now() - timedelta(days=5)), "end": iso(local_now() - timedelta(days=2))})
    assert too_long.status_code == 422


def test_each_person_only_sees_and_changes_their_own_fasts(wger):
    admin, ana = two_people()
    admin.post("/api/fasting/start", json={"at": iso(local_now() - timedelta(hours=3))})
    fast_id = admin.get("/api/fasting").json()["active"]["id"]
    assert ana.get("/api/fasting").json()["active"] is None
    assert ana.patch(f"/api/fasting/{fast_id}", json={"start": iso(local_now() - timedelta(hours=1))}).status_code == 404
    assert ana.delete(f"/api/fasting/{fast_id}").status_code == 404
    assert ana.post("/api/fasting/end", json={}).status_code == 409
    assert admin.get("/api/fasting").json()["active"]["id"] == fast_id
    edited = admin.patch(f"/api/fasting/{fast_id}", json={"start": iso(local_now() - timedelta(hours=5))}).json()
    assert edited["active"]["hours"] >= 4.9
    assert admin.delete(f"/api/fasting/{fast_id}").json()["active"] is None


@pytest.mark.parametrize("health, reason", [({"pregnancy": 2}, "pregnancy"), ({"diabetes": True}, "diabetes"), ({"ed_risk": True}, "ed")])
def test_fasting_is_not_offered_when_it_could_harm(wger, health, reason):
    admin, _ = two_people()
    store.update_user(me_id(admin), health=json.dumps(health))
    state = admin.get("/api/fasting").json()
    assert state["blocked"] == reason and state["blocked_text"]
    assert admin.post("/api/fasting/start", json={}).status_code == 403
    start = local_now() - timedelta(days=1)
    assert admin.post("/api/fasting/past", json={"start": iso(start), "end": iso(start + timedelta(hours=14))}).status_code == 403


def test_minors_underweight_and_self_exclusion_are_blocked(wger):
    admin, ana = two_people()
    young = (local_now().date() - timedelta(days=365 * 16)).isoformat()
    store.update_user(me_id(admin), birthdate=young)
    assert admin.get("/api/fasting").json()["blocked"] == "minor"
    store.update_user(me_id(ana), height_cm=170)
    store.set_weight(me_id(ana), local_now().date().isoformat(), 50)
    assert ana.get("/api/fasting").json()["blocked"] == "underweight"


def test_saying_one_of_the_cautions_applies_turns_fasting_off(wger):
    admin, _ = two_people()
    assert admin.post("/api/fasting/intro", json={"none_apply": False}).json()["blocked"] == "self"
    assert admin.post("/api/fasting/start", json={}).status_code == 403
    state = admin.post("/api/fasting/intro", json={"none_apply": True}).json()
    assert state["blocked"] is None and state["plan"]["intro_done"]


def test_reminders_are_pure_and_respect_blocks():
    now = datetime.fromisoformat("2026-11-17T20:05:00-05:00")
    base = {"blocked": None, "active": None, "plan": {"chosen": True, "start": "20:00", "label": "16:8"}}
    assert [k for k, _, _ in fasting.due_reminders(base, {"on": True}, now)] == ["fast_start"]
    assert fasting.due_reminders(base, {"on": False}, now) == []
    assert fasting.due_reminders({**base, "blocked": "diabetes"}, {"on": True}, now) == []
    started = now - timedelta(hours=16, minutes=3)
    active = {"id": 7, "started_at": started.isoformat(), "planned_h": 16, "ends_at": (started + timedelta(hours=16)).isoformat()}
    keys = [k for k, _, _ in fasting.due_reminders({**base, "active": active}, {"on": True, "half": True}, now)]
    assert keys == ["fast_end:7"]


def test_scheduler_sends_the_fasting_reminder_once(wger, monkeypatch):
    sent = []
    monkeypatch.setattr(webpush, "send", lambda sub, message, *a: sent.append(message))
    admin, _ = two_people()
    admin.post("/api/push/subscribe", json=SUB)
    admin.put("/api/fasting/plan", json={"hours": 14, "start": "20:00"})
    admin.put("/api/reminders", json={"fasting": {"on": True}})
    assert admin.get("/api/reminders").json()["prefs"]["fasting"] == {"on": True, "half": False}
    at = local_now().replace(hour=20, minute=3, second=0, microsecond=0)
    assert reminders.run_once(at) == 1
    assert reminders.run_once(at + timedelta(minutes=1)) == 0
