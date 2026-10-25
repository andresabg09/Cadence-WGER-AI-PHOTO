"""One-shot health report for the whole chain (config -> wger -> Gemini).

Exposed at GET /api/diagnostics. It only ever returns booleans and short
messages - never keys, tokens or user data - so it is safe to open in a
browser while setting the system up, and it replaces the guess-and-redeploy
loop: one deploy, one report, every missing piece listed with its fix.

?deep=1 additionally makes one real call to Gemini and logs + deletes a 1 g
diary entry in wger, which validates the exact write path /api/confirm uses.
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
    found: dict[str, int] = {}  # ids discovered by earlier checks, reused by later ones

    _run(checks, "WGER_API_TOKEN configurado",
         "Pon WGER_API_TOKEN en la pestana Entorno de EasyPanel (con 'Crear archivo .env' activado) y vuelve a implementar.",
         lambda: (_require(bool(settings.wger_api_token), "vacio"), "ok")[1])
    _run(checks, "GEMINI_API_KEY configurado",
         "Pon GEMINI_API_KEY en la pestana Entorno de EasyPanel y vuelve a implementar.",
         lambda: (_require(bool(settings.gemini_api_key), "vacio"), "ok")[1])

    if wger is not None:
        _wger_checks(checks, found, wger, deep)

    if deep and settings.gemini_api_key:
        def gemini() -> str:
            from google import genai

            reply = genai.Client(api_key=settings.gemini_api_key).models.generate_content(
                model=settings.gemini_model, contents="Responde solo la palabra: ok"
            )
            _require(bool((reply.text or "").strip()), "respuesta vacia")
            return f"modelo {settings.gemini_model} responde"

        _run(checks, "Gemini responde",
             "Revisa GEMINI_API_KEY y GEMINI_MODEL (nombre vigente en ai.google.dev/gemini-api/docs/models).", gemini)

        def interview() -> str:
            """A made-up person goes through the interview prompt in one message: the reading must be valid and sensible."""
            from . import coach
            from .vision import GeminiVisionClient

            said = ("Soy cajera de un supermercado, paso de pie unas 8 horas y camino unos 20 minutos para llegar al trabajo. "
                    "Entreno pesas 3 veces por semana, 45 minutos cada vez, desde hace 6 meses. No cuento mis pasos.")
            client = GeminiVisionClient(settings.gemini_api_key, settings.gemini_model)
            raw = client.chat_json(coach._interview_system("muscle", coach.MAX_USER_TURNS), [{"role": "user", "text": said}])  # noqa: SLF001
            data = coach.parse_json_object(raw)
            _require(data is not None and bool(data.get("done")), "la IA no termino la entrevista con un caso completo")
            activity = coach.validate_activity(data.get("activity"))
            _require(activity is not None, "la lectura de la IA no es valida")
            _require(activity.lifestyle in ("light", "moderate"), f"nivel inesperado para una cajera de pie: {activity.lifestyle}")
            _require(any(t.kind == "pesas" for t in activity.training), "no entendio que entrena pesas")
            return f"entiende un caso de prueba (nivel {activity.lifestyle}, {len(activity.training)} entrenamiento)"

        _run(checks, "Entrevista de actividad entiende un caso de prueba",
             "Gemini no devolvio una lectura valida de la entrevista: copiame este mensaje completo y ajusto el prompt.", interview)

    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def _wger_checks(checks: list[dict], found: dict[str, int], wger: WgerClient, deep: bool) -> None:
    client = wger._client  # noqa: SLF001 - diagnostics may use the raw client

    def reachable() -> str:
        client.get("/api/v2/", headers={"Authorization": ""}).raise_for_status()
        return settings.wger_base_url

    if not _run(checks, "wger responde",
                "Revisa WGER_BASE_URL: debe ser la URL publica de tu wger, sin barra final.", reachable):
        return

    def token_valid() -> str:
        response = client.get("/api/v2/nutritionplan/", params={"format": "json", "limit": 5})
        if response.status_code in (401, 403):
            raise RuntimeError("wger rechazo el token")
        response.raise_for_status()
        plans = response.json().get("results", [])
        if plans:
            found["plan"] = max(p["id"] for p in plans)
        return "token valido"

    valid = _run(checks, "Token de wger valido",
                 "Copia de nuevo la clave en wger -> menu de usuario -> API key (solo la clave, sin 'Token ').", token_valid)

    if valid:
        def plan() -> str:
            if "plan" in found:
                return "plan existente"
            if not deep:
                return "se creara solo al registrar la primera comida"
            found["plan"] = wger.create_nutrition_plan()
            return "plan creado automaticamente"

        _run(checks, "Plan de nutricion (lo crea cadence solo)",
             "wger rechazo crear el plan: avisame con este mensaje.", plan)

        def diary() -> str:
            from datetime import datetime, timedelta, timezone

            now = datetime.now(timezone.utc)
            wger.get_diary_entries(found.get("plan", 0), now - timedelta(days=1), now)
            return "lectura del diario ok"

        _run(checks, "Diario de comidas accesible",
             "El filtro datetime__gte/lte del diario no coincide con tu version de wger: avisame con este mensaje.", diary)

    def ingredients() -> str:
        response = client.get("/api/v2/ingredientinfo/", params={"limit": 1, "format": "json"})
        response.raise_for_status()
        results = response.json().get("results")
        _require(bool(results), "el catalogo esta vacio")
        found["ingredient"] = results[0]["id"]
        return "catalogo con datos"

    loaded = _run(checks, "wger tiene ingredientes cargados",
                  "En la terminal del contenedor 'web' ejecuta: python3 manage.py sync-ingredients-bulk (tarda varios minutos).",
                  ingredients)

    if loaded and valid:
        _run(checks, "Busqueda de ingredientes funciona",
             "La busqueda no devuelve resultados para 'chicken': revisa WGER_LANGUAGE_CODE o avisame.",
             lambda: (_require(bool(wger.search_ingredients("chicken", limit=3)), "sin resultados"), "ok")[1])

    if deep and "plan" in found and "ingredient" in found:
        def write_test() -> str:
            entry_id = wger.log_diary_entry(found["plan"], found["ingredient"], 1)
            wger.delete_diary_entry(entry_id)
            return "registro de prueba creado y borrado"

        _run(checks, "Registrar y borrar una comida de prueba",
             "wger rechazo el registro: avisame con este mensaje (probablemente un campo de /nutritiondiary/ distinto en tu version).",
             write_test)

    if deep and "plan" in found:
        def staple_write_test() -> str:
            from datetime import timedelta

            from .meals import datetime_for_meal, local_now

            staples = wger.list_staples()
            _require(bool(staples), "no hay alimentos basicos cargados (seed_staples.py)")
            # Same shape as a real confirm: a basic food, dated yesterday inside the breakfast window.
            when = datetime_for_meal("desayuno", local_now() - timedelta(days=1))
            entry_id = wger.log_diary_entry(found["plan"], staples[0]["id"], 1, when)
            wger.delete_diary_entry(entry_id)
            return f"registro de prueba con '{staples[0]['name']}' creado y borrado"

        _run(checks, "Registrar un alimento basico de cadence (fecha de ayer)",
             "wger rechazo registrar un alimento basico: copiame este mensaje completo.", staple_write_test)
