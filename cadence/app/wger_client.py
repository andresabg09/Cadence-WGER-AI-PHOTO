import logging
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger("cadence.wger")


STAPLES_SOURCE = "cadence"


class WgerError(RuntimeError):
    pass


class _Reject(Exception):
    """The internal route answered like a wrong door (bad host, redirect, gateway error)."""


class _Http:
    """One long-lived connection pool to wger, shared by every request of the process.

    A fresh client per request meant a new TLS handshake to wger's PUBLIC address (out to the internet and
    back through the proxy) on every call. With `internal` set, calls go straight to the nginx container on
    the Docker network, presenting the public Host so wger sees what it always saw. If that route is not
    there (or looks wrong on its first answer), it falls back to the public address and retries later."""

    BAD_FIRST = {301, 302, 307, 308, 400, 502, 503, 504}

    def __init__(self, public: httpx.Client, internal: httpx.Client | None = None):
        self.public = public
        self.internal = internal
        self._checked = False
        self._down_until = 0.0

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        if self.internal is not None and time.monotonic() >= self._down_until:
            try:
                response = self.internal.request(method, url, **kwargs)
                if not self._checked:
                    if response.status_code in self.BAD_FIRST:
                        raise _Reject(response.status_code)
                    self._checked = True
                return response
            except (httpx.ConnectError, httpx.ConnectTimeout, _Reject) as exc:
                logger.warning("ruta interna a wger no disponible (%s): uso la direccion publica 5 minutos", exc)
                self._down_until = time.monotonic() + 300
                self._checked = False
        return self.public.request(method, url, **kwargs)

    def get(self, url, **kw): return self.request("GET", url, **kw)
    def post(self, url, **kw): return self.request("POST", url, **kw)
    def patch(self, url, **kw): return self.request("PATCH", url, **kw)
    def put(self, url, **kw): return self.request("PUT", url, **kw)
    def delete(self, url, **kw): return self.request("DELETE", url, **kw)
    def close(self) -> None: pass  # shared for the life of the process


_pools: dict[tuple, _Http] = {}
_pools_lock = threading.Lock()
_ingredients: dict[int, tuple[float, dict]] = {}  # a food's nutrition does not change: remember it
INGREDIENT_TTL = 6 * 3600
INGREDIENT_MAX = 6000


def _shared_http(base_url: str, token: str, internal_url: str) -> _Http:
    key = (base_url, token, internal_url)
    with _pools_lock:
        pool = _pools.get(key)
        if pool is None:
            limits = httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=60)
            headers = {"Authorization": f"Token {token}"}
            public = httpx.Client(base_url=base_url, headers=headers, timeout=15.0, limits=limits)
            internal = None
            if internal_url:
                host = urlsplit(base_url)
                internal = httpx.Client(
                    base_url=internal_url.rstrip("/"), timeout=15.0, limits=limits,
                    headers={**headers, "Host": host.netloc, "X-Forwarded-Proto": host.scheme or "https"},
                )
            pool = _pools[key] = _Http(public, internal)
        return pool


class WgerClient:
    """Thin client over wger's own REST API - never a separate database.

    Every calorie value cadence ever shows comes from wger's nutrition
    database via this client; the vision model never supplies one.
    """

    def __init__(self, base_url: str, api_token: str, language_id: int = 2, language_code: str = "en",
                 internal_url: str = ""):
        self._base_url = base_url.rstrip("/")
        self._language_id = language_id
        self._language_code = language_code
        self._client = _shared_http(self._base_url, api_token, internal_url)

    def search_ingredients(self, term: str, limit: int = 15) -> list[dict]:
        """Text search in wger's ingredient DB.

        Recent wger versions dropped /ingredient/search/ (404) in favour of
        /ingredientinfo/?name__search= (what wger's own mobile app uses), which
        also returns the nutrition values inline. The legacy endpoint is kept
        as a fallback for older instances.
        """
        response = self._client.get(
            "/api/v2/ingredientinfo/",
            params={
                "name__search": term,
                "language__code": self._language_code,
                "limit": limit,
                "format": "json",
            },
        )
        if response.status_code != 404:
            response.raise_for_status()
            return [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "image": item.get("image"),
                    "energy": item.get("energy"),
                    "protein": item.get("protein"),
                    "carbohydrates": item.get("carbohydrates"),
                    "fat": item.get("fat"),
                    "source": item.get("source_name"),
                }
                for item in response.json().get("results", [])
                if item.get("id") is not None
            ]
        return self._search_ingredients_legacy(term, limit)

    def list_staples(self) -> list[dict]:
        """The ready-to-eat staples loaded by scripts/seed_staples.py (source_name=cadence)."""
        response = self._client.get(
            "/api/v2/ingredientinfo/",
            params={"source_name": STAPLES_SOURCE, "limit": 500, "format": "json"},
        )
        response.raise_for_status()
        return [
            {
                "id": item.get("id"), "name": item.get("name"), "image": item.get("image"),
                "energy": item.get("energy"), "protein": item.get("protein"),
                "carbohydrates": item.get("carbohydrates"), "fat": item.get("fat"), "source": STAPLES_SOURCE,
            }
            for item in response.json().get("results", [])
            if item.get("id") is not None
        ]

    def get_ingredient_by_code(self, code: str) -> dict | None:
        """A product by barcode. wger itself falls back to Open Food Facts (and stores the
        product) when its own catalog lacks the code."""
        response = self._client.get("/api/v2/ingredientinfo/", params={"code": code, "limit": 1, "format": "json"})
        response.raise_for_status()
        results = response.json().get("results", [])
        if not results or results[0].get("id") is None:
            return None
        item = results[0]
        return {"id": item["id"], "name": item.get("name"), "image": item.get("image"), "energy": item.get("energy"),
                "protein": item.get("protein"), "carbohydrates": item.get("carbohydrates"), "fat": item.get("fat")}

    def _search_ingredients_legacy(self, term: str, limit: int) -> list[dict]:
        response = self._client.get(
            "/api/v2/ingredient/search/",
            params={"term": term, "language": self._language_id, "format": "json"},
        )
        response.raise_for_status()
        data = response.json()
        # wger wraps results as {"suggestions": [{"data": {...}, "value": "..."}]}
        suggestions = data.get("suggestions", data if isinstance(data, list) else [])
        results = []
        for item in suggestions[:limit]:
            payload = item.get("data", item)
            results.append(
                {
                    "id": payload.get("id"),
                    "name": payload.get("name") or item.get("value"),
                    "image": payload.get("image"),
                }
            )
        return [r for r in results if r["id"] is not None]

    def find_default_nutrition_plan_id(self) -> int | str | None:
        response = self._client.get("/api/v2/nutritionplan/", params={"format": "json", "limit": 5})
        response.raise_for_status()
        results = response.json().get("results", [])
        # wger doesn't expose an "active plan" flag by default; the most recently
        # created plan is the logging target. Ids may be UUIDs, so order by date.
        if not results:
            return None
        return max(results, key=lambda p: (p.get("creation_date") or "", str(p["id"])))["id"]

    def find_legacy_plan_id(self) -> int | str | None:
        """The plan used before cadence had accounts (description "cadence", not "cadence:<user id>").

        It holds the administrator's earlier diary, so the first account adopts it.
        """
        response = self._client.get("/api/v2/nutritionplan/", params={"format": "json", "limit": 100})
        response.raise_for_status()
        legacy = [p for p in response.json().get("results", [])
                  if not str(p.get("description", "")).startswith("cadence:")]
        if not legacy:
            return None
        return max(legacy, key=lambda p: (p.get("creation_date") or "", str(p["id"])))["id"]

    def create_nutrition_plan(self, description: str = "cadence") -> int | str:
        """wger needs every diary entry to belong to a plan; cadence creates one per person
        so nobody ever has to open wger just to make one."""
        response = self._client.post(
            "/api/v2/nutritionplan/",
            json={"description": description, "only_logging": True},
        )
        if response.status_code >= 400:
            raise WgerError(f"wger rechazo crear el plan de nutricion: {response.status_code} {response.text}")
        return response.json()["id"]

    def get_default_nutrition_plan_id(self) -> int | str:
        return self.find_default_nutrition_plan_id() or self.create_nutrition_plan()

    def get_nutrition_plan(self, plan_id: int) -> dict:
        response = self._client.get(f"/api/v2/nutritionplan/{plan_id}/", params={"format": "json"})
        response.raise_for_status()
        return response.json()

    def get_diary_entries(self, plan_id: int, start: datetime, end: datetime) -> list[dict]:
        """Entries for `plan_id` logged between two *aware* datetimes.

        wger's /nutritiondiary/ endpoint filters by "datetime" range via
        datetime__gte / datetime__lte - TODO verify these exact filter param
        names against the real instance (same caveat as the rest of this
        client: implemented per the known v2 schema, not yet tested live).
        """
        results: list[dict] = []
        offset = 0
        for _ in range(20):  # 20 pages of 500 is far beyond a personal diary
            response = self._client.get(
                "/api/v2/nutritiondiary/",
                params={
                    "plan": plan_id,
                    "datetime__gte": start.isoformat(),
                    "datetime__lte": end.isoformat(),
                    "format": "json",
                    "limit": 500,
                    "offset": offset,
                },
            )
            response.raise_for_status()
            body = response.json()
            page = body.get("results", [])
            results.extend(page)
            if not body.get("next") or not page:
                break
            offset += len(page)
        return results

    def get_ingredient(self, ingredient_id: int) -> dict:
        now = time.monotonic()
        hit = _ingredients.get(ingredient_id)
        if hit and now - hit[0] < INGREDIENT_TTL:
            return hit[1]
        response = self._client.get(f"/api/v2/ingredient/{ingredient_id}/", params={"format": "json"})
        response.raise_for_status()
        data = response.json()
        if len(_ingredients) >= INGREDIENT_MAX:
            _ingredients.clear()
        _ingredients[ingredient_id] = (now, data)
        return data

    def log_diary_entry(
        self,
        plan_id: int,
        ingredient_id: int,
        amount_grams: float,
        when: datetime | None = None,
    ) -> str:
        payload = {
            "plan": plan_id,
            "ingredient": ingredient_id,
            "amount": amount_grams,
            "datetime": (when or datetime.now(timezone.utc)).isoformat(),
        }
        response = self._client.post("/api/v2/nutritiondiary/", json=payload)
        if response.status_code >= 400:
            raise WgerError(f"wger rechazo el registro de comida: {response.status_code} {response.text}")
        return str(response.json()["id"])

    def update_diary_entry(self, entry_id: int | str, amount_grams: float | None = None,
                           when: datetime | None = None) -> None:
        payload: dict = {}
        if amount_grams is not None:
            payload["amount"] = amount_grams
        if when is not None:
            payload["datetime"] = when.isoformat()
        response = self._client.patch(f"/api/v2/nutritiondiary/{entry_id}/", json=payload)
        if response.status_code >= 400:
            raise WgerError(f"wger rechazo el cambio del registro: {response.status_code} {response.text}")

    def get_diary_entry(self, entry_id: int | str) -> dict:
        response = self._client.get(f"/api/v2/nutritiondiary/{entry_id}/", params={"format": "json"})
        if response.status_code >= 400:
            raise WgerError(f"wger no encontro el registro: {response.status_code}")
        return response.json()

    def delete_diary_entry(self, entry_id: int | str) -> None:
        response = self._client.delete(f"/api/v2/nutritiondiary/{entry_id}/")
        if response.status_code not in (200, 202, 204):
            raise WgerError(f"wger rechazo el borrado del registro: {response.status_code} {response.text}")

    def close(self) -> None:
        self._client.close()
