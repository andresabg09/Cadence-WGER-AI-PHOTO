# cadence (servicio)

Extension propia sobre wger: reconocimiento automatico de comida por foto
usando IA. No modifica el core de wger, solo consume su API REST. Ver
[`../CLAUDE.md`](../CLAUDE.md) para el contexto completo del proyecto.

## Flujo

1. `POST /api/analyze` recibe una foto (`multipart/form-data`, campo
   `image`).
2. Gemini Flash (Lite) identifica cada componente del plato por separado,
   sin calcular calorias.
3. Por cada componente, se busca en `/api/v2/ingredient/search/` de wger y
   se reordenan los resultados con fuzzy matching local (`rapidfuzz`) para
   devolver 2-3 candidatos.
4. El cliente (ver `static/camera.html`) muestra los candidatos, el usuario
   elige uno y un gramaje por componente.
5. `POST /api/confirm` crea los registros via `POST
   /api/v2/nutritiondiary/` de wger.

Las calorias **siempre** salen de la base de datos de wger - la IA de
vision solo identifica, nunca calcula nutricion.

## Correr localmente (sin Docker)

```bash
cd cadence
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # y completa GEMINI_API_KEY / WGER_API_TOKEN
uvicorn app.main:app --reload --port 8001
```

Abre `http://localhost:8001/` para la interfaz de camara, o llama a los
endpoints directamente.

## Tests

```bash
cd cadence
pip install -r requirements.txt pytest
pytest tests/
```

Cubre la logica de fuzzy matching (`matching.py`), que es pura y no
depende de red. `vision.py` y `wger_client.py` no tienen tests
automatizados todavia porque requieren credenciales reales (Gemini API key,
token de wger) - **verificar manualmente contra la instancia real antes de
confiar en el flujo de `/api/confirm`**, especialmente los nombres de
campos de `/api/v2/nutritiondiary/`, que pueden variar segun la version de
wger desplegada.

## Variables de entorno

Ver `.env.example` para la lista completa y comentada. Las dos que
requieren generar algo manualmente:

- `GEMINI_API_KEY` - desde [Google AI Studio](https://aistudio.google.com/).
- `WGER_API_TOKEN` - en wger: menu de usuario -> API key (o
  `/en/user/api-key`), con la instancia ya desplegada.

## Despliegue

Este servicio se construye como parte del `docker-compose.yml` de la raiz
del repo (servicio `cadence`, build desde esta carpeta) y se expone via
nginx en `/cadence/` (con slash final). Ver `../deploy/README.md` para el
mecanismo de despliegue automatico al hacer push.
