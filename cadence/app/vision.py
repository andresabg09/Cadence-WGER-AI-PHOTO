import json
import re

from google import genai
from google.genai import types

from .schemas import DetectedComponent

# The model only names what it sees. Calories always come from wger's
# nutrition database afterwards - never from the vision model itself.
_PROMPT = """
Eres un identificador de alimentos. Observa la foto de un plato de comida y
lista cada componente/ingrediente por separado (no el plato como un todo).

Reglas estrictas:
- NO calcules ni menciones calorias, macros ni cantidades nutricionales.
- Identifica cada componente por separado, ej: "pollo a la plancha", "arroz
  blanco", "ensalada de lechuga y tomate", en vez de "plato de pollo con arroz".
- Usa nombres genericos de alimento (los que usarias para buscarlo en una
  base de datos nutricional), no nombres de marcas ni platos compuestos.
- Da un valor de confianza entre 0 y 1 para cada componente.
- "estimated_grams": peso aproximado en gramos de ESA porcion tal como se ve
  en la foto (entero). Si el plato es una sola unidad (una paleta, una barra,
  una manzana), reparte su peso total entre los componentes que la forman.
  Es solo una estimacion de porcion: NO es un dato nutricional.
- "name" va en espanol (es lo que ve el usuario). "search_name" es el mismo
  alimento como nombre generico corto en ingles (ej: "grilled chicken breast",
  "white rice"), porque la base de datos nutricional esta en ingles.

Responde UNICAMENTE con un JSON array, sin texto adicional, con esta forma:
[{"name": "pollo a la plancha", "search_name": "grilled chicken breast", "confidence": 0.9, "estimated_grams": 120}, ...]
"""


class GeminiVisionClient:
    def __init__(self, api_key: str, model: str):
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def identify_components(self, image_bytes: bytes, mime_type: str) -> list[DetectedComponent]:
        response = self._client.models.generate_content(
            model=self._model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                _PROMPT,
            ],
        )
        return _parse_components(response.text or "")


def _parse_components(raw_text: str) -> list[DetectedComponent]:
    # Gemini sometimes wraps JSON in ```json fences despite instructions.
    match = re.search(r"\[.*\]", raw_text, re.DOTALL)
    payload = match.group(0) if match else raw_text
    data = json.loads(payload)
    return [
        DetectedComponent(
            name=item["name"],
            search_name=item.get("search_name"),
            confidence=item.get("confidence"),
            estimated_grams=_sane_grams(item.get("estimated_grams")),
        )
        for item in data
    ]


def _sane_grams(value) -> int | None:
    """Keep the model's portion guess only when it is a plausible single-plate weight."""
    try:
        grams = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return grams if 5 <= grams <= 1500 else None
