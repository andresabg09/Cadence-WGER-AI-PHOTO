import os
import tempfile

os.environ.setdefault("GEMINI_API_KEY", "x")
os.environ.setdefault("WGER_API_TOKEN", "x")

import pytest

from app import accounts, main, store
from app.auth import current_user
from app.config import settings


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch):
    """Every test gets its own empty data folder (accounts, notes, photos)."""
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(settings, "data_dir", tmp)
        monkeypatch.setattr(settings, "open_registration", False)
        monkeypatch.setattr(settings, "admin_email", "")
        accounts._login_throttle._hits.clear()  # failed-login counters live in memory
        accounts._register_throttle._hits.clear()
        yield tmp


@pytest.fixture(autouse=True)
def fresh_caches():
    """Reads are remembered for minutes in production; every test starts with nothing remembered."""
    from app import main, wger_client
    main._entries_cache.clear()
    main._entries_gen.clear()
    wger_client._ingredients.clear()
    yield


@pytest.fixture(autouse=True)
def signed_in(request, isolated_store):
    """Most tests are about food, not login: they run as the administrator, who owns wger plan 1.

    Tests marked `@pytest.mark.anonymous` skip this and use the real cookie login.
    """
    if request.node.get_closest_marker("anonymous"):
        yield None
        return
    user, _ = store.create_user("admin@example.com", "Admin", "x", None, False)
    store.update_user(user.id, plan_id="1", onboarded=True)
    main.app.dependency_overrides[current_user] = lambda: store.get_user(user.id)
    yield user
    main.app.dependency_overrides.pop(current_user, None)
