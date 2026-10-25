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
- AGUA: si ves agua sola (un vaso, botella o jarra con agua sin sabor, sin azucar,
  sin leche ni jugo) NO es un alimento: devuelvela como un elemento con
  "name": "agua" y "water_ml": los mililitros que se ven (entero; un vaso lleno
  ~250, una botella pequena ~500, una grande ~1000; ajusta si esta a medias).
  Un refresco, jugo, leche, cafe o te NO es agua: listalo como alimento normal.
- "name" va en espanol (es lo que ve el usuario). "search_name" es el mismo
  alimento como nombre generico corto en ingles y TAL COMO SE COME (cocido o
  preparado, no crudo): "cooked white rice", "grilled chicken breast",
  "boiled egg", "vanilla ice cream". La base de datos nutricional esta en ingles.
- "search_alternatives": hasta 3 nombres alternativos cortos en ingles del MISMO
  alimento, de lo mas especifico a lo mas general ("chicken noodle soup",
  "chicken soup", "chicken broth"). Sirven para encontrarlo si la base lo nombra distinto.
- "liquid": true SOLO si ese componente se mide en mililitros (una sopa, un caldo, un
  jugo, un batido, leche, cafe, un refresco); omitelo o pon false en sólidos.

Responde UNICAMENTE con un JSON array, sin texto adicional, con esta forma:
[{"name": "pollo a la plancha", "search_name": "grilled chicken breast", "search_alternatives": ["chicken breast", "grilled chicken"], "confidence": 0.9, "estimated_grams": 120, "box_2d": [250, 100, 700, 480]}, {"name": "sopa de pollo", "search_name": "chicken soup", "search_alternatives": ["chicken broth"], "liquid": true, "confidence": 0.8, "estimated_grams": 300, "box_2d": [100, 600, 500, 950]}, {"name": "agua", "water_ml": 250, "confidence": 0.9}]
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
- "liquid": true SOLO si se mide en mililitros (sopa, caldo, jugo, batido, leche, cafe,
  refresco); si dijo "un vaso de leche" o "un plato de sopa", convierte a gramos (1 ml = 1 g).
- "confidence": 0 a 1, que tan seguro estas de haber entendido ese alimento.
- Agua sola ("un vaso de agua", "medio litro de agua"): elemento con "name": "agua"
  y "water_ml" en mililitros (un vaso ~250, una botella ~500, un litro 1000). No es un
  alimento. Refresco, jugo, leche o cafe SI son alimentos.
- Si el audio no menciona ningun alimento o no se entiende, responde [].

Responde UNICAMENTE con un JSON array, sin texto adicional:
[{"name": "pollo a la plancha", "search_name": "grilled chicken breast", "search_alternatives": ["chicken breast"], "confidence": 0.9, "estimated_grams": 200}]
"""


_TRANSCRIBE_PROMPT = """
Transcribe el audio en espanol, palabra por palabra, tal como se dijo. Escribe solo el texto, con puntuacion normal, sin comillas, sin
comentarios y sin traducir. Si no se entiende nada o no hay voz, responde con una linea vacia.
"""


_IDEAS_PROMPT = """
Eres un asistente practico de comidas para una persona en Panama/Latinoamerica. Sugiere {count} ideas de {meal}
sencillas, con ingredientes comunes y faciles de conseguir. La persona aun puede comer unas {kcal} kcal y unos {protein} g
de proteina hoy: usa eso solo como guia para elegir porciones razonables (comidas ligeras si queda poco, completas si queda mucho).

Reglas estrictas:
- NO escribas calorias, macros ni cantidades nutricionales en la respuesta. Solo nombres de platos, ingredientes y gramos.
- Cada idea lleva de 2 a 5 ingredientes, cada uno con su peso aproximado en gramos (entero) tal como se come.
- "name" de la idea y de cada ingrediente en espanol, cortos. "search_name": el ingrediente como nombre generico corto en
  ingles y TAL COMO SE COME (cooked/grilled/boiled): "plain yogurt", "cooked oatmeal", "banana".
  "search_alternatives": hasta 2 nombres alternativos en ingles.
- "tag": una sola palabra entre "Rapida", "Ligera", "Completa", "Alta en proteina" (o null).
- Las ideas deben ser distintas entre si. Evita lo que ya comio hoy: {eaten}.
{liked}
Responde UNICAMENTE con un JSON array, sin texto adicional:
[{{"name": "Yogur con avena y banano", "tag": "Rapida", "items": [{{"name": "yogur natural", "search_name": "plain yogurt", "search_alternatives": ["yogurt"], "grams": 200}}, {{"name": "avena cocida", "search_name": "cooked oatmeal", "search_alternatives": [], "grams": 150}}]}}]
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


    def suggest_meals(self, *, meal: str, kcal_left: int, protein_left: int, eaten: list[str], liked: list[str], count: int = 4) -> list[dict]:
        """Meal ideas as names, ingredients and grams. The calories are looked up in wger afterwards, never asked of the model."""
        prompt = _IDEAS_PROMPT.format(
            count=count, meal=meal, kcal=kcal_left, protein=protein_left, eaten=", ".join(eaten[:12]) or "nada todavia",
            liked=f"Cosas que esta persona come seguido (puedes inspirarte, sin repetirlas igual): {', '.join(liked[:10])}." if liked else "")
        response = self._client.models.generate_content(model=self._model, contents=[prompt])
        return _parse_ideas(response.text or "[]")

    def _turns(self, turns: list[dict], audio: tuple[bytes, str] | None) -> list:
        """The conversation as Gemini wants it. `audio` is the person's latest message, spoken."""
        contents = [types.Content(role="model" if t["role"] == "assistant" else "user", parts=[types.Part.from_text(text=t["text"])])
                    for t in turns if t.get("text")]
        if audio:
            contents.append(types.Content(role="user", parts=[types.Part.from_bytes(data=audio[0], mime_type=audio[1])]))
        return contents or [types.Content(role="user", parts=[types.Part.from_text(text="Empieza.")])]

    def chat_json(self, system: str, turns: list[dict], audio: tuple[bytes, str] | None = None) -> str:
        """One turn of a conversation whose answer is JSON (the activity interview). Raw text back: the caller validates it."""
        response = self._client.models.generate_content(
            model=self._model, contents=self._turns(turns, audio),
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.3, response_mime_type="application/json"))
        return response.text or ""

    def chat_text(self, system: str, turns: list[dict]) -> str:
        """One turn of a conversation whose answer is plain text (the assistant)."""
        response = self._client.models.generate_content(
            model=self._model, contents=self._turns(turns, None),
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.4))
        return response.text or ""

    def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        """What was said, word for word, as plain text (dictation: the person reads and edits it before sending anything)."""
        response = self._client.models.generate_content(
            model=self._model,
            contents=[types.Part.from_bytes(data=audio_bytes, mime_type=mime_type), _TRANSCRIBE_PROMPT],
        )
        return (response.text or "").strip()

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
            name=item.get("name") or "agua",
            water_ml=_sane_ml(item.get("water_ml")),
            search_name=item.get("search_name"),
            search_alternatives=_alternatives(item.get("search_alternatives")),
            confidence=item.get("confidence"),
            estimated_grams=_sane_grams(item.get("estimated_grams")),
            box=_box_from_gemini(item.get("box_2d")),
            liquid=item.get("liquid") if isinstance(item.get("liquid"), bool) else None,
        )
        for item in data
    ]


TAGS = {"rapida": "Rápida", "ligera": "Ligera", "completa": "Completa", "alta en proteina": "Alta en proteína"}


def _parse_ideas(raw_text: str) -> list[dict]:
    match = re.search(r"\[.*\]", raw_text, re.DOTALL)
    try:
        data = json.loads(match.group(0) if match else raw_text)
    except ValueError:
        return []
    ideas = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            continue
        items = []
        for part in item.get("items") or []:
            grams = _sane_grams(part.get("grams")) if isinstance(part, dict) else None
            if grams and str(part.get("name") or "").strip():
                items.append({"name": str(part["name"]).strip()[:60], "search_name": (part.get("search_name") or "").strip() or None,
                              "search_alternatives": _alternatives(part.get("search_alternatives")), "grams": grams})
        if len(items) >= 2:
            tag = TAGS.get(re.sub(r"\s+", " ", str(item.get("tag") or "").lower().replace("á", "a").replace("í", "i")).strip())
            ideas.append({"name": str(item["name"]).strip()[:70], "tag": tag, "items": items[:5]})
    return ideas[:6]


def _alternatives(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(term).strip() for term in raw if str(term).strip()][:3]


def _sane_ml(value) -> int | None:
    try:
        ml = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return ml if 20 <= ml <= 3000 else None


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
