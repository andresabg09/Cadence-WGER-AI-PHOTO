"""One-shot health report for the whole chain (config -> wger -> Gemini).

Exposed at GET /api/diagnostics. It only ever returns booleans and short
messages - never keys, tokens or user data - so it is safe to open in a
browser while setting the system up, and it replaces the guess-and-redeploy
loop: one deploy, one report, every missing piece listed with its fix.
"""

from collections.abc import Callable

import httpx

from .config import settings
from .wger_client import WgerClient


def _run(checks: list[dict], name: str, fix: str, fn: Callable[[], str]) -> bool:
    try:
        detail = fn()
        checks.append({"name": name, "ok": True, "detail": detail, "fix": None})
        return True
    except Exception as exc:  # noqa: BLE001 - a report must never raise
        if isinstance(exc, httpx.HTTPStatusError):
            detail = f"wger respondio {exc.response.status_code} en {exc.request.url.path}"
        else:
            detail = str(exc) or type(exc).__name__
        checks.append({"name": name, "ok": False, "detail": detail, "fix": fix})
        return False


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_diagnostics(wger: WgerClient | None, deep: bool = False) -> dict:
    checks: list[dict] = []

    _run(checks, "WGER_API_TOKEN configurado", "Pon WGER_API_TOKEN en la pestana Entorno de EasyPanel (con 'Crear archivo .env' activado) y vuelve a implementar.",
         lambda: (_require(bool(settings.wger_api_token), "vacio"), "ok")[1])
    _run(checks, "GEMINI_API_KEY configurado", "Pon GEMINI_API_KEY en la pestana Entorno de EasyPanel y vuelve a implementar.",
         lambda: (_require(bool(settings.gemini_api_key), "vacio"), "ok")[1])

    if wger is None:
        return {"ok": False, "checks": checks}

    client = wger._client  # noqa: SLF001 - diagnostics may use the raw client

    def reachable() -> str:
        client.get("/api/v2/", headers={"Authorization": ""}).raise_for_status()
        return settings.wger_base_url

    reached = _run(checks, "wger responde", "Revisa WGER_BASE_URL: debe ser la URL publica de tu wger, sin barra final.", reachable)

    if reached:
        plans: list = []

        def token_valid() -> str:
            response = client.get("/api/v2/nutritionplan/", params={"format": "json", "limit": 5})
            if response.status_code in (401, 403):
                raise RuntimeError("wger rechazo el token")
            response.raise_for_status()
            plans.extend(response.json().get("results", []))
            return "token valido"

        valid = _run(checks, "Token de wger valido", "Copia de nuevo la clave en wger -> menu de usuario -> API key (formato: solo la clave, sin 'Token ').", token_valid)

        if valid:
            _run(checks, "Existe un plan de nutricion", "En wger entra a Nutricion y crea un plan (el nombre da igual).",
                 lambda: (_require(bool(plans), "no hay ningun plan"), f"{len(plans)} plan(es)")[1])

            def diary() -> str:
                from datetime import datetime, timedelta, timezone
                now = datetime.now(timezone.utc)
                wger.get_diary_entries(plans[0]["id"] if plans else 0, now - timedelta(days=1), now)
                return "lectura del diario ok"

            _run(checks, "Diario de comidas accesible", "El filtro datetime__gte/lte del diario no coincide con tu version de wger: avisame con este mensaje.", diary)

        def ingredients() -> str:
            response = client.get("/api/v2/ingredientinfo/", params={"limit": 1, "format": "json"})
            response.raise_for_status()
            _require(bool(response.json().get("results")), "el catalogo esta vacio")
            return "catalogo con datos"

        loaded = _run(checks, "wger tiene ingredientes cargados", "En la terminal del contenedor 'web' ejecuta: python3 manage.py sync-ingredients-bulk (tarda varios minutos).", ingredients)

        if loaded and valid:
            _run(checks, "Busqueda de ingredientes funciona", "La busqueda no devuelve resultados para 'chicken': revisa WGER_LANGUAGE_CODE o avisame.",
                 lambda: (_require(bool(wger.search_ingredients("chicken", limit=3)), "sin resultados"), "ok")[1])

    if deep and settings.gemini_api_key:
        def gemini() -> str:
            from google import genai
            reply = genai.Client(api_key=settings.gemini_api_key).models.generate_content(
                model=settings.gemini_model, contents="Responde solo la palabra: ok"
            )
            _require(bool((reply.text or "").strip()), "respuesta vacia")
            return f"modelo {settings.gemini_model} responde"

        _run(checks, "Gemini responde", "Revisa GEMINI_API_KEY y GEMINI_MODEL (nombre vigente en ai.google.dev/gemini-api/docs/models).", gemini)

    return {"ok": all(c["ok"] for c in checks), "checks": checks}
