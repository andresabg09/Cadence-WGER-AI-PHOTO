"""Carga REDUCIDA del catalogo de alimentos en wger (se ejecuta dentro del contenedor `web`).

El volcado oficial de wger.de trae ~3 millones de productos (casi todos de supermercado,
en muchos idiomas) y en un servidor pequeno el comando oficial se demora horas. Para
cadence basta un catalogo de alimentos genericos, en ingles y espanol, sin duplicados:

    python3 manage.py shell -c "exec(open('/tmp/load_ingredients.py').read())"

Variables opcionales: PER_LANG (por idioma, defecto 40000), LANGS (defecto "en,es").
Las calorias siguen saliendo de wger: este script solo decide QUE alimentos se cargan.
"""
import glob
import gzip
import json
import os
import re
import time
import urllib.request

DUMP_URL = "https://wger.de/media/ingredients/ingredients.jsonl.gz"
DUMP_DEST = "/tmp/ingredients.jsonl.gz"
PER_LANG = int(os.environ.get("PER_LANG", "40000"))
LANG_CODES = [c.strip() for c in os.environ.get("LANGS", "en,es").split(",") if c.strip()]
BATCH = 1000
_DIGITS = re.compile(r"\d")


def find_dump() -> str:
    candidates = [p for p in glob.glob("/tmp/*.jsonl.gz") if os.path.getsize(p) > 100_000_000]
    if candidates:
        return max(candidates, key=os.path.getmtime)
    print("Descargando el volcado de wger.de ...", flush=True)
    urllib.request.urlretrieve(DUMP_URL, DUMP_DEST)
    return DUMP_DEST


def classify(data: dict, lang_ids: set) -> tuple[tuple, str] | None:
    """Return (score, key) for a usable generic food, else None. Lower score = better:
    unbranded first, then the SHORTEST name (short names are the generic foods:
    "Rice", "White rice", "Chicken breast"; long ones are products)."""
    language = data.get("language")
    if isinstance(language, dict):
        language = language.get("id")
    if language not in lang_ids or not data.get("uuid"):
        return None

    name = (data.get("name") or "").strip()
    if not 3 <= len(name) <= 50 or _DIGITS.search(name):
        return None
    brand = (data.get("brand") or "").strip()
    if brand and brand.lower() in name.lower():
        return None  # "Nutella", "Coca-Cola ...": a product, not a food

    try:
        energy, protein, carbs, fat = (float(data[k]) for k in ("energy", "protein", "carbohydrates", "fat"))
    except (KeyError, TypeError, ValueError):
        return None
    if not 0 < energy <= 900 or min(protein, carbs, fat) < 0 or protein + carbs + fat > 100.5:
        return None
    if protein + carbs + fat == 0:
        return None

    score = (1 if brand else 0, len(name), 0 if data.get("fiber") is not None else 1)
    return score, f"{language}:{name.lower()}"


def select(lines, lang_ids: set, per_lang: int, progress=lambda n: None):
    """Stream the dump once; keep the per_lang best (most generic) unique foods per language.

    Memory stays bounded: each language's candidate pool is pruned to the best
    per_lang whenever it grows past 3x that."""
    pools = {lid: {} for lid in lang_ids}  # lang -> {key: (score, data)}
    seen = 0
    for line in lines:
        seen += 1
        if seen % 500_000 == 0:
            progress(seen)
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        verdict = classify(data, lang_ids)
        if verdict is None:
            continue
        score, key = verdict
        language = data["language"]["id"] if isinstance(data["language"], dict) else data["language"]
        pool = pools[language]
        if key not in pool or score < pool[key][0]:
            pool[key] = (score, data)
        if len(pool) > per_lang * 3:
            best = sorted(pool.items(), key=lambda kv: kv[1][0])[:per_lang]
            pools[language] = dict(best)
    chosen = []
    for pool in pools.values():
        chosen.extend(d for _score, d in sorted(pool.values(), key=lambda sd: sd[0])[:per_lang])
    return chosen, seen


def main():
    from wger.core.models import Language
    from wger.nutrition.extract_info.wger import extract_info_from_wger_api
    from wger.nutrition.models import Ingredient

    languages = {lang.id: lang.short_name for lang in Language.objects.filter(short_name__in=LANG_CODES)}
    print("Idiomas a cargar:", languages, flush=True)
    if not languages:
        print("No se encontro ningun idioma; revisa LANGS.")
        return

    path = find_dump()
    print("Leyendo", path, flush=True)
    started = time.time()
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        chosen, seen = select(handle, set(languages), PER_LANG,
                              progress=lambda n: print(f"  {n:,} lineas leidas ({time.time() - started:.0f}s)", flush=True))
    per = {}
    for item in chosen:
        lid = item["language"]["id"] if isinstance(item["language"], dict) else item["language"]
        per[languages[lid]] = per.get(languages[lid], 0) + 1
    print(f"Leidas {seen:,} lineas. Seleccionados {len(chosen):,} alimentos: {per}", flush=True)

    inserted, errors, warned = 0, 0, False
    started = time.time()
    for start in range(0, len(chosen), BATCH):
        objs = []
        for data in chosen[start:start + BATCH]:
            try:
                fields = extract_info_from_wger_api(data).dict()
                fields["uuid"] = data["uuid"]
                objs.append(Ingredient(**fields))
            except Exception:  # noqa: BLE001 - one bad record must not stop the load
                errors += 1
        try:
            Ingredient.objects.bulk_create(objs, ignore_conflicts=True)
            inserted += len(objs)
        except Exception as exc:  # noqa: BLE001
            if not warned:
                print("bulk_create fallo, se guardan uno por uno. Motivo:", repr(exc)[:300], flush=True)
                warned = True
            for obj in objs:
                try:
                    obj.save()
                    inserted += 1
                except Exception:  # noqa: BLE001
                    errors += 1
        done = start + BATCH
        if done % 5000 < BATCH:
            rate = inserted / max(time.time() - started, 1)
            print(f"  guardados {inserted:,}/{len(chosen):,} ({rate:.0f}/s)", flush=True)

    print(f"LISTO: {inserted:,} guardados, {errors:,} descartados.", flush=True)
    print("En la base hay ahora:", Ingredient.objects.count(), "alimentos.", flush=True)
    for term in ("chicken", "rice", "pollo", "arroz"):
        print(f"  '{term}':", Ingredient.objects.filter(name__icontains=term).count(), flush=True)


if not os.environ.get("CADENCE_NO_RUN"):
    main()
