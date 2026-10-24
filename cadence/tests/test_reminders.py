"""Reminders: what is due when, the push plumbing (checked against RFC 8291's own test vector) and privacy."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from app import main, reminders, store, webpush
from tests.test_accounts import new_client, register
from tests.test_foods import CatalogWger

pytestmark = pytest.mark.anonymous
PANAMA = ZoneInfo("America/Panama")


def at(day, hhmm):  # 2026-10-25 is a Sunday
    return datetime.fromisoformat(f"2026-10-{day}T{hhmm}:00").replace(tzinfo=PANAMA)


def test_rfc8291_example_encrypts_to_the_published_bytes():
    key = ec.derive_private_key(int.from_bytes(webpush.b64u_decode("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"), ec.SECP256R1())
    body = webpush.encrypt(b"When I grow up, I want to be a watermelon",
                           "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4", "BTBZMqHH6r4Tts7J_aSIgg",
                           salt=webpush.b64u_decode("DGv6ra1nlYgDCS1FRnbzlw"), sender_key=key)
    assert webpush.b64u(body) == ("DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_"
                                  "yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


def test_vapid_token_is_signed_by_the_published_key():
    private, public = webpush.generate_vapid_keys()
    header = webpush.vapid_headers("https://push.example.com/send/abc", private, public, "mailto:a@b.co")["Authorization"]
    token = header.split("t=")[1].split(",")[0]
    signing, signature = token.rsplit(".", 1)
    raw = webpush.b64u_decode(signature)
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), webpush.b64u_decode(public)).verify(der, signing.encode(), ec.ECDSA(hashes.SHA256()))


def test_what_is_due_and_when():
    prefs = {"water": {"on": True, "every_h": 2, "from": "08:00", "to": "12:00"},
             "meals": {"almuerzo": {"on": True, "time": "12:30"}}, "weekly": {"on": True, "time": "09:00"}}
    assert [r.key for r in reminders.due_reminders(prefs, at("24", "10:10"))] == ["water:1000"]
    assert [r.key for r in reminders.due_reminders(prefs, at("24", "10:31"))] == []  # window is 30 min
    assert [r.key for r in reminders.due_reminders(prefs, at("24", "14:00"))] == []  # after "to"; also past the lunch window
    assert [r.key for r in reminders.due_reminders(prefs, at("24", "12:45"))] == ["meal:almuerzo"]
    assert "weekly" in [r.key for r in reminders.due_reminders(prefs, at("25", "09:05"))]  # Sunday
    assert "weekly" not in [r.key for r in reminders.due_reminders(prefs, at("24", "09:05"))]
    assert reminders.due_reminders({}, at("24", "08:00")) == []  # everything off by default


def test_prefs_are_cleaned():
    cleaned = reminders.clean_prefs({"water": {"on": 1, "every_h": 9, "from": "8am"}, "meals": {"cena": {"on": True, "time": "25:99"}}})
    assert cleaned["water"] == {"on": True, "every_h": 2, "from": "08:00", "to": "22:00"}
    assert cleaned["meals"]["cena"] == {"on": True, "time": "19:30"} and cleaned["meals"]["desayuno"]["on"] is False


@pytest.fixture
def world(monkeypatch):
    fake = CatalogWger()
    monkeypatch.setattr(main, "get_wger_client", lambda: fake)
    sent = []
    monkeypatch.setattr(webpush, "send", lambda sub, message, *a: sent.append((sub["endpoint"], message)))
    admin, ana = new_client(), new_client()
    register(admin, "admin@example.com")
    register(ana, "ana@example.com", admin.post("/api/admin/invites", json={}).json()["code"])
    return admin, ana, sent


SUB = {"endpoint": "https://push.example.com/send/abc", "keys": {"p256dh": "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4", "auth": "BTBZMqHH6r4Tts7J_aSIgg"}}


def test_subscribe_prefs_test_push_and_privacy(world):
    admin, ana, sent = world
    key = admin.get("/api/push/key").json()["public_key"]
    assert len(webpush.b64u_decode(key)) == 65 and admin.get("/api/push/key").json()["public_key"] == key  # stable
    assert new_client().get("/api/push/key").status_code == 401
    assert admin.post("/api/push/test").status_code == 409  # no device yet
    assert admin.post("/api/push/subscribe", json={"endpoint": "http://insecure", "keys": SUB["keys"]}).status_code == 422
    assert admin.post("/api/push/subscribe", json=SUB).json() == {"devices": 1}
    assert admin.post("/api/push/test").json() == {"sent": 1} and sent[0][0] == SUB["endpoint"]
    assert ana.post("/api/push/test").status_code == 409  # her device list is empty
    ana.post("/api/push/unsubscribe", json=SUB)
    assert admin.get("/api/reminders").json()["devices"] == 1  # she cannot remove his device
    assert admin.put("/api/reminders", json={"meals": {"cena": {"on": True, "time": "19:00"}}}).json()["prefs"]["meals"]["cena"]["on"] is True
    assert ana.get("/api/reminders").json()["prefs"]["meals"]["cena"]["on"] is False


def test_scheduler_sends_once_per_day_and_skips_a_logged_meal(world, monkeypatch):
    admin, ana, sent = world
    admin.post("/api/push/subscribe", json=SUB)
    admin.put("/api/reminders", json={"meals": {"cena": {"on": True, "time": "19:00"}, "almuerzo": {"on": True, "time": "12:30"}}})
    me = admin.get("/api/auth/me").json()
    made = admin.post("/api/foods", json={"name": "Sopa", "kcal": 50}).json()
    store.add_local_entry(me["id"], made["id"], 200, at("24", "12:40"))  # lunch is already logged
    assert reminders.run_once(at("24", "12:45")) == 0
    assert reminders.run_once(at("24", "19:02")) == 1
    assert reminders.run_once(at("24", "19:03")) == 0  # same day, same reminder
    assert [m["tag"] for _, m in sent] == ["meal:cena"] and sent[0][1]["url"] == "scan.html?meal=cena"
    assert reminders.run_once(at("25", "19:02")) == 1  # next day it comes back


def test_a_dead_device_is_forgotten(world, monkeypatch):
    admin, _, _ = world
    admin.post("/api/push/subscribe", json=SUB)

    def gone(*a):
        raise webpush.Gone("x")
    monkeypatch.setattr(webpush, "send", gone)
    assert admin.post("/api/push/test").status_code == 502
    assert admin.get("/api/reminders").json()["devices"] == 0
