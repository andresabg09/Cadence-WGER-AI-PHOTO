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
- "box_2d": donde esta ESE componente en la foto, como [ymin, xmin, ymax, xmax]
  con valores enteros de 0 a 1000 (0,0 es la esquina superior izquierda de la
  foto, 1000,1000 la inferior derecha). Encierra solo ese componente, ajustado,
  no todo el plato; las cajas de componentes distintos pueden tocarse.
- "name" va en espanol (es lo que ve el usuario). "search_name" es el mismo
  alimento como nombre generico corto en ingles y TAL COMO SE COME (cocido o
  preparado, no crudo): "cooked white rice", "grilled chicken breast",
  "boiled egg", "vanilla ice cream". La base de datos nutricional esta en ingles.
- "search_alternatives": hasta 3 nombres alternativos cortos en ingles del MISMO
  alimento, de lo mas especifico a lo mas general ("chicken noodle soup",
  "chicken soup", "chicken broth"). Sirven para encontrarlo si la base lo nombra distinto.

Responde UNICAMENTE con un JSON array, sin texto adicional, con esta forma:
[{"name": "pollo a la plancha", "search_name": "grilled chicken breast", "search_alternatives": ["chicken breast", "grilled chicken"], "confidence": 0.9, "estimated_grams": 120, "box_2d": [250, 100, 700, 480]}, ...]
"""


_AUDIO_PROMPT = """
Eres un asistente que anota comidas. Escucha el audio: una persona dice, en espanol,
lo que comio o va a comer (por ejemplo "registra doscientos gramos de pollo a la plancha
con una taza de arroz").

Reglas estrictas:
- Lista cada alimento mencionado por separado. Ignora todo lo que no sea comida.
- NO calcules ni menciones calorias ni macros.
- "estimated_grams": los gramos que dijo; si dijo otra medida, conviertela a gramos
  aproximados (una taza de arroz cocido ~160, un huevo ~50, una rebanada de pan ~30,
  un vaso de leche ~250, una cucharada ~15). Si no dijo cantidad, una porcion normal.
- "name" va en espanol, tal como lo dijo (corto). "search_name" es el mismo alimento
  como nombre generico corto en ingles y TAL COMO SE COME (cooked/grilled/boiled).
  "search_alternatives": hasta 3 nombres alternativos en ingles, de mas a menos especifico.
- "confidence": 0 a 1, que tan seguro estas de haber entendido ese alimento.
- Si el audio no menciona ningun alimento o no se entiende, responde [].

Responde UNICAMENTE con un JSON array, sin texto adicional:
[{"name": "pollo a la plancha", "search_name": "grilled chicken breast", "search_alternatives": ["chicken breast"], "confidence": 0.9, "estimated_grams": 200}]
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


    def identify_from_audio(self, audio_bytes: bytes, mime_type: str) -> list[DetectedComponent]:
        response = self._client.models.generate_content(
            model=self._model,
            contents=[types.Part.from_bytes(data=audio_bytes, mime_type=mime_type), _AUDIO_PROMPT],
        )
        return _parse_components(response.text or "[]")


def _parse_components(raw_text: str) -> list[DetectedComponent]:
    # Gemini sometimes wraps JSON in ```json fences despite instructions.
    match = re.search(r"\[.*\]", raw_text, re.DOTALL)
    payload = match.group(0) if match else raw_text
    data = json.loads(payload)
    return [
        DetectedComponent(
            name=item["name"],
            search_name=item.get("search_name"),
            search_alternatives=_alternatives(item.get("search_alternatives")),
            confidence=item.get("confidence"),
            estimated_grams=_sane_grams(item.get("estimated_grams")),
            box=_box_from_gemini(item.get("box_2d")),
        )
        for item in data
    ]


def _alternatives(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(term).strip() for term in raw if str(term).strip()][:3]


def _sane_grams(value) -> int | None:
    """Keep the model's portion guess only when it is a plausible single-plate weight."""
    try:
        grams = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return grams if 5 <= grams <= 1500 else None


def _box_from_gemini(raw) -> list[float] | None:
    """Gemini boxes are [ymin, xmin, ymax, xmax] on a 0-1000 grid; the UI wants
    [x, y, width, height] as 0-1 fractions of the photo. Anything implausible is
    dropped (the UI then falls back to the whole photo)."""
    try:
        ymin, xmin, ymax, xmax = (float(v) for v in raw)
    except (TypeError, ValueError):
        return None
    ymin, xmin = max(0.0, ymin), max(0.0, xmin)
    ymax, xmax = min(1000.0, ymax), min(1000.0, xmax)
    width, height = (xmax - xmin) / 1000, (ymax - ymin) / 1000
    if width < 0.03 or height < 0.03:
        return None
    return [round(xmin / 1000, 4), round(ymin / 1000, 4), round(width, 4), round(height, 4)]
