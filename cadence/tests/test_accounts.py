"""Accounts: sign-up rules, sessions, the first-run plan, and - above all - that people stay apart."""

import base64
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import main, store
from app.config import settings
from app.meals import local_now

pytestmark = pytest.mark.anonymous  # these tests use the real cookie login

PNG = "data:image/png;base64," + base64.b64encode(
    base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")
).decode()
PROFILE = {"sex": "male", "birthdate": "1990-05-10", "height_cm": 178, "weight_kg": 80, "activity": "moderate", "goal": "lose"}


class SharedWger:
    """One wger account shared by everybody: separation is cadence's job."""

    def __init__(self):
        self.entries: list[dict] = []
        self.next_plan = 10
        self.plans = [{"id": 1, "description": "cadence", "creation_date": "2026-10-01"}]

    def find_legacy_plan_id(self):
        legacy = [p for p in self.plans if not p["description"].startswith("cadence:")]
        return legacy[-1]["id"] if legacy else None

    def create_nutrition_plan(self, description="cadence"):
        self.next_plan += 1
        self.plans.append({"id": self.next_plan, "description": description, "creation_date": "2026-10-25"})
        return self.next_plan

    def log_diary_entry(self, plan, ingredient, grams, when):
        entry_id = f"e{len(self.entries) + 1}"
        self.entries.append({"id": entry_id, "plan": int(plan), "ingredient": ingredient, "amount": grams, "datetime": when.isoformat()})
        return entry_id

    def get_diary_entries(self, plan, start, end):
        return [e for e in self.entries if e["plan"] == int(plan) and start <= datetime.fromisoformat(e["datetime"]) <= end]

    def get_diary_entry(self, entry_id):
        found = [e for e in self.entries if e["id"] == entry_id]
        if not found:
            from app.wger_client import WgerError
            raise WgerError("no existe")
        return found[0]

    def delete_diary_entry(self, entry_id): self.entries = [e for e in self.entries if e["id"] != entry_id]
    def update_diary_entry(self, entry_id, amount_grams=None, when=None):
        for e in self.entries:
            if e["id"] == entry_id and amount_grams is not None: e["amount"] = amount_grams
    def get_ingredient(self, ingredient_id): return {"name": "Arroz", "energy": 130, "protein": 2.7, "carbohydrates": 28, "fat": 0.3}
    def close(self): pass


@pytest.fixture
def wger(monkeypatch):
    fake = SharedWger()
    monkeypatch.setattr(main, "get_wger_client", lambda: fake)
    return fake


def new_client():
    return TestClient(main.app, raise_server_exceptions=False)  # each client has its own cookie jar


def register(http, email, invite=None, password="clave-segura-1", name="Persona"):
    return http.post("/api/auth/register", json={"email": email, "name": name, "password": password, "invite": invite})


def test_nothing_is_reachable_without_signing_in(wger):
    http = new_client()
    for method, path in [("get", "/api/today"), ("get", "/api/calendar"), ("get", "/api/streaks"), ("get", "/api/auth/me"),
                         ("get", "/api/search?term=a"), ("get", "/api/recent"), ("delete", "/api/diary/e1"),
                         ("get", "/api/media/crop/e1"), ("get", "/api/admin/overview"), ("get", "/api/diagnostics")]:
        assert getattr(http, method)(path).status_code == 401, path
    assert http.post("/api/analyze", files={"image": ("p.jpg", b"x", "image/jpeg")}).status_code == 401
    assert http.get("/health").status_code == 200 and http.get("/api/auth/status").json() == {"first_user": True, "invite_required": True}


def test_first_account_is_admin_the_rest_need_a_single_use_invite(wger):
    admin = new_client()
    assert register(admin, "Andres@Example.com").status_code == 200
    me = admin.get("/api/auth/me").json()
    assert me["is_admin"] and me["email"] == "andres@example.com" and not me["onboarded"]

    other = new_client()
    assert register(other, "ana@example.com").status_code == 403  # no invite
    assert register(other, "ana@example.com", "AAAA-BBBB").status_code == 403  # made-up code
    code = admin.post("/api/admin/invites", json={"note": "Ana"}).json()["code"]
    assert other.post("/api/admin/invites", json={}).status_code == 401  # not signed in yet
    assert register(other, "ana@example.com", code.lower()).status_code == 200
    assert not other.get("/api/auth/me").json()["is_admin"]
    assert register(new_client(), "luis@example.com", code).status_code == 403  # already used
    assert other.get("/api/admin/overview").status_code == 403 and other.post("/api/admin/invites", json={}).status_code == 403
    assert register(admin, "ana@example.com", code).status_code == 409  # e-mail taken


def test_admin_email_setting_locks_who_can_claim_the_first_account(wger, monkeypatch):
    monkeypatch.setattr(settings, "admin_email", "andres@example.com")
    assert register(new_client(), "intruso@example.com").status_code == 403
    assert register(new_client(), "ANDRES@example.com").status_code == 200


def test_login_logout_and_wrong_passwords(wger):
    http = new_client()
    register(http, "a@example.com", password="clave-segura-1")
    assert http.post("/api/auth/logout").status_code == 200
    assert http.get("/api/auth/me").status_code == 401
    assert http.post("/api/auth/login", json={"email": "a@example.com", "password": "mala-clave"}).status_code == 401
    assert http.post("/api/auth/login", json={"email": "nadie@example.com", "password": "mala-clave"}).status_code == 401
    assert http.post("/api/auth/login", json={"email": "A@example.com", "password": "clave-segura-1"}).status_code == 200
    assert http.get("/api/auth/me").status_code == 200
    assert register(new_client(), "b@example.com", password="corta").status_code == 422  # 8+ characters


def test_repeated_failures_lock_the_login_for_a_while(wger):
    http = new_client()
    register(http, "a@example.com")
    for _ in range(8):
        http.post("/api/auth/login", json={"email": "a@example.com", "password": "x" * 9})
    assert http.post("/api/auth/login", json={"email": "a@example.com", "password": "clave-segura-1"}).status_code == 429


def test_first_run_questionnaire_calculates_and_stores_the_plan(wger):
    http = new_client()
    register(http, "a@example.com")
    preview = http.post("/api/plan/preview", json=PROFILE).json()
    assert 1800 < preview["kcal"] < 2800 and preview["protein_g"] > 100
    me = http.put("/api/profile", json=PROFILE).json()
    assert me["onboarded"] and me["profile"]["weight_kg"] == 80 and me["targets"]["kcal"] == preview["kcal"]
    # a manual nudge keeps macros coherent
    adjusted = http.put("/api/goals", json={"kcal": preview["kcal"] + 200}).json()["targets"]
    assert adjusted["kcal"] == preview["kcal"] + 200 and adjusted["carbs_g"] > preview["carbs_g"]
    gain = http.put("/api/goals", json={"goal": "gain"}).json()["targets"]
    assert gain["kcal"] > preview["kcal"]
    today = http.get("/api/today").json()
    assert today["goal"]["kcal"] == gain["kcal"] and today["user_name"] == "Persona"
    assert http.put("/api/profile", json={**PROFILE, "birthdate": "2024-01-01"}).status_code == 422  # too young
    assert http.put("/api/profile", json={**PROFILE, "goal": "volar"}).status_code == 422


def test_people_cannot_see_or_touch_each_others_diary(wger):
    admin, ana = new_client(), new_client()
    register(admin, "admin@example.com")
    code = admin.post("/api/admin/invites", json={}).json()["code"]
    register(ana, "ana@example.com", code)

    body = {"items": [{"ingredient_id": 5, "amount_grams": 100}], "meal": "almuerzo"}
    mine = admin.post("/api/confirm", json=body).json()["created"][0]["diary_entry_id"]
    hers = ana.post("/api/confirm", json=body).json()["created"][0]["diary_entry_id"]
    assert wger.entries[0]["plan"] == 1 and wger.entries[1]["plan"] != 1  # the admin kept the old plan; Ana got her own

    assert [m["items"][0]["diary_entry_id"] for m in admin.get("/api/today").json()["meals"]] == [mine]
    assert [m["items"][0]["diary_entry_id"] for m in ana.get("/api/today").json()["meals"]] == [hers]

    # Ana tries everything on the admin's entry
    assert ana.delete(f"/api/diary/{mine}").status_code == 404
    assert ana.patch(f"/api/diary/{mine}", json={"amount_grams": 1}).status_code == 404
    assert ana.put(f"/api/diary/{mine}/note", json={"note": "hackeado"}).status_code == 404
    media = {"plate_id": mine, "photos": [PNG], "items": [{"entry_id": mine, "crop": PNG, "photo": 0}]}
    assert ana.post("/api/entry-media", json=media).status_code == 404
    assert len(wger.entries) == 2 and wger.entries[0]["amount"] == 100

    # the owner stores a photo; Ana cannot download it, even knowing the ids
    assert admin.post("/api/entry-media", json=media).json() == {"saved": 1}
    assert admin.get(f"/api/media/crop/{mine}").status_code == 200
    assert ana.get(f"/api/media/crop/{mine}").status_code == 404
    assert ana.get(f"/api/media/plate/1-{mine}:0").status_code == 404 and admin.get(f"/api/media/plate/1-{mine}:0").status_code == 200

    # a plan id sent by the client is ignored
    assert ana.post("/api/confirm", json={**body, "plan_id": 1}).status_code == 200
    assert all(e["plan"] != 1 for e in wger.entries[2:])
    assert len(admin.get("/api/calendar").json()["days"]) == 1 and len(ana.get("/api/calendar").json()["days"]) == 1


def test_streaks_are_per_person(wger):
    admin, ana = new_client(), new_client()
    register(admin, "admin@example.com")
    ana_code = admin.post("/api/admin/invites", json={}).json()["code"]
    register(ana, "ana@example.com", ana_code)
    body = {"items": [{"ingredient_id": 5, "amount_grams": 100}], "meal": "almuerzo"}
    admin.post("/api/confirm", json=body)
    assert admin.get("/api/today").json()["streak_days"] == 1 and ana.get("/api/today").json()["streak_days"] == 0


def test_daily_photo_limit_protects_the_ai_bill(wger, monkeypatch):
    monkeypatch.setattr(settings, "analyze_daily_limit", 2)
    admin, ana = new_client(), new_client()
    register(admin, "admin@example.com")
    register(ana, "ana@example.com", admin.post("/api/admin/invites", json={}).json()["code"])

    class NoFood:
        def identify_components(self, image_bytes, mime): return []

    monkeypatch.setattr(main, "get_vision_client", lambda: NoFood())
    upload = {"image": ("p.jpg", b"x", "image/jpeg")}
    assert [ana.post("/api/analyze", files=upload).status_code for _ in range(3)] == [422, 422, 429]
    assert admin.post("/api/analyze", files=upload).status_code == 422  # the administrator is exempt


def test_password_change_and_admin_reset(wger):
    admin, ana = new_client(), new_client()
    register(admin, "admin@example.com")
    register(ana, "ana@example.com", admin.post("/api/admin/invites", json={}).json()["code"], password="clave-segura-1")
    assert ana.post("/api/auth/password", json={"current": "mala", "new": "nueva-clave-9"}).status_code == 403
    assert ana.post("/api/auth/password", json={"current": "clave-segura-1", "new": "nueva-clave-9"}).status_code == 200
    assert ana.get("/api/auth/me").status_code == 200
    ana_id = [u for u in admin.get("/api/admin/overview").json()["users"] if u["email"] == "ana@example.com"][0]["id"]
    temp = admin.post(f"/api/admin/users/{ana_id}/reset-password").json()["password"]
    assert ana.get("/api/auth/me").status_code == 401  # signed out everywhere
    assert new_client().post("/api/auth/login", json={"email": "ana@example.com", "password": temp}).status_code == 200
