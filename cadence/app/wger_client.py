from datetime import datetime, timezone

import httpx


class WgerError(RuntimeError):
    pass


class WgerClient:
    """Thin client over wger's own REST API - never a separate database.

    Every calorie value cadence ever shows comes from wger's nutrition
    database via this client; the vision model never supplies one.
    """

    def __init__(self, base_url: str, api_token: str, language_id: int = 2):
        self._base_url = base_url.rstrip("/")
        self._language_id = language_id
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Token {api_token}"},
            timeout=15.0,
        )

    def search_ingredients(self, term: str, limit: int = 15) -> list[dict]:
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

    def get_default_nutrition_plan_id(self) -> int:
        response = self._client.get("/api/v2/nutritionplan/", params={"format": "json", "limit": 5})
        response.raise_for_status()
        results = response.json().get("results", [])
        if not results:
            raise WgerError(
                "No hay ningun plan de nutricion en wger para este usuario. "
                "Crea uno manualmente en la app o via POST /api/v2/nutritionplan/ "
                "antes de registrar comidas."
            )
        # wger doesn't expose an "active plan" flag by default; the most
        # recently created plan (highest id) is used as the logging target.
        return max(results, key=lambda p: p["id"])["id"]

    def log_diary_entry(
        self,
        plan_id: int,
        ingredient_id: int,
        amount_grams: float,
        when: datetime | None = None,
    ) -> int:
        payload = {
            "plan": plan_id,
            "ingredient": ingredient_id,
            "amount": amount_grams,
            "datetime": (when or datetime.now(timezone.utc)).isoformat(),
        }
        response = self._client.post("/api/v2/nutritiondiary/", json=payload)
        if response.status_code >= 400:
            raise WgerError(f"wger rechazo el registro de comida: {response.status_code} {response.text}")
        return response.json()["id"]

    def close(self) -> None:
        self._client.close()
