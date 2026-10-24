from datetime import datetime, timezone

import httpx


class WgerError(RuntimeError):
    pass


class WgerClient:
    """Thin client over wger's own REST API - never a separate database.

    Every calorie value cadence ever shows comes from wger's nutrition
    database via this client; the vision model never supplies one.
    """

    def __init__(self, base_url: str, api_token: str, language_id: int = 2, language_code: str = "en"):
        self._base_url = base_url.rstrip("/")
        self._language_id = language_id
        self._language_code = language_code
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Token {api_token}"},
            timeout=15.0,
        )

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
                }
                for item in response.json().get("results", [])
                if item.get("id") is not None
            ]
        return self._search_ingredients_legacy(term, limit)

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

    def create_nutrition_plan(self) -> int | str:
        """wger needs every diary entry to belong to a plan; cadence creates its own
        so the user never has to open wger just to make one."""
        response = self._client.post(
            "/api/v2/nutritionplan/",
            json={"description": "cadence", "only_logging": True},
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
        response = self._client.get(
            "/api/v2/nutritiondiary/",
            params={
                "plan": plan_id,
                "datetime__gte": start.isoformat(),
                "datetime__lte": end.isoformat(),
                "format": "json",
                "limit": 500,
            },
        )
        response.raise_for_status()
        return response.json().get("results", [])

    def get_ingredient(self, ingredient_id: int) -> dict:
        response = self._client.get(f"/api/v2/ingredient/{ingredient_id}/", params={"format": "json"})
        response.raise_for_status()
        return response.json()

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

    def delete_diary_entry(self, entry_id: int | str) -> None:
        response = self._client.delete(f"/api/v2/nutritiondiary/{entry_id}/")
        if response.status_code not in (200, 202, 204):
            raise WgerError(f"wger rechazo el borrado del registro: {response.status_code} {response.text}")

    def close(self) -> None:
        self._client.close()
