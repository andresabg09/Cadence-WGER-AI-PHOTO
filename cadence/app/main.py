from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .matching import rank_candidates
from .schemas import AnalyzeResponse, ComponentMatch, ConfirmedEntry, ConfirmRequest, ConfirmResponse
from .vision import GeminiVisionClient
from .wger_client import WgerClient, WgerError

app = FastAPI(title="cadence", version="0.1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

_vision_client: GeminiVisionClient | None = None


def get_vision_client() -> GeminiVisionClient:
    global _vision_client
    if _vision_client is None:
        if not settings.gemini_api_key:
            raise HTTPException(500, "GEMINI_API_KEY no esta configurado")
        _vision_client = GeminiVisionClient(settings.gemini_api_key, settings.gemini_model)
    return _vision_client


def get_wger_client() -> WgerClient:
    if not settings.wger_api_token:
        raise HTTPException(500, "WGER_API_TOKEN no esta configurado")
    return WgerClient(settings.wger_base_url, settings.wger_api_token, settings.wger_language_id)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def camera_page():
    return FileResponse("static/camera.html")


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(image: UploadFile):
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(400, "Imagen vacia")

    vision = get_vision_client()
    detected = vision.identify_components(image_bytes, image.content_type or "image/jpeg")
    if not detected:
        raise HTTPException(422, "No se identifico ningun alimento en la foto")

    wger = get_wger_client()
    try:
        components = []
        for component in detected:
            raw_matches = wger.search_ingredients(component.name)
            candidates = rank_candidates(component.name, raw_matches, settings.match_candidate_count)
            components.append(
                ComponentMatch(
                    detected_name=component.name,
                    confidence=component.confidence,
                    candidates=candidates,
                )
            )
    finally:
        wger.close()

    return AnalyzeResponse(components=components)


@app.post("/api/confirm", response_model=ConfirmResponse)
def confirm(request: ConfirmRequest):
    wger = get_wger_client()
    try:
        plan_id = request.plan_id or settings.default_nutrition_plan_id or wger.get_default_nutrition_plan_id()

        created = []
        for item in request.items:
            try:
                diary_entry_id = wger.log_diary_entry(plan_id, item.ingredient_id, item.amount_grams)
            except WgerError as exc:
                raise HTTPException(502, str(exc)) from exc
            created.append(
                ConfirmedEntry(
                    ingredient_id=item.ingredient_id,
                    amount_grams=item.amount_grams,
                    diary_entry_id=diary_entry_id,
                )
            )
        return ConfirmResponse(created=created)
    finally:
        wger.close()
