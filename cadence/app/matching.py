from rapidfuzz import fuzz

from .schemas import IngredientCandidate


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace(",", " ").split())


def match_score(wanted: str, candidate: str) -> float:
    """0..100. WRatio finds the words; plain ratio punishes extra words, so
    "Vanilla ice cream" beats "Cherry vanilla ice cream, cherry vanilla"."""
    a, b = _norm(wanted), _norm(candidate)
    return (fuzz.WRatio(a, b) + fuzz.ratio(a, b)) / 2


STAPLE_BONUS = 20  # ready-to-eat staples beat "as sold" supermarket products of a similar name


def _macros(item: dict) -> tuple:
    return tuple(item.get(k) for k in ("energy", "protein", "carbohydrates", "fat"))


def rank_matches(wanted: str, raw_matches: list[dict], top_n: int, alt: str | None = None) -> list[tuple[float, dict]]:
    """Best matches first. `alt` is the same food in the user's own words (Spanish), so
    "arroz blanco" finds "Arroz blanco cocido" too.

    Curated staples get a bonus. A staple exists in English and Spanish with the same
    macros ("twins"): the pair ranks by whichever name matched better but is shown once,
    in the user's language when we know it (the `alt` wording)."""
    scored: list[tuple[float, dict]] = []
    twins: dict[tuple, list[tuple[float, float, dict]]] = {}
    for item in raw_matches:
        main = match_score(wanted, item["name"])
        other = match_score(alt, item["name"]) if alt else 0.0
        if item.get("source") == "cadence":
            twins.setdefault(_macros(item), []).append((main, other, item))
        else:
            scored.append((max(main, other + 1), item))

    for group in twins.values():
        best = max(max(main, other + 1) for main, other, _ in group) + STAPLE_BONUS
        # shown in the user's language: the twin that matches the `alt` wording best
        shown = max(group, key=lambda t: t[1] if alt else t[0])[2]
        scored.append((best, shown))

    # Ties: the shorter (more generic) name first.
    scored.sort(key=lambda pair: (-pair[0], len(pair[1]["name"])))
    return scored[:top_n]


def rank_candidates(
    detected_name: str,
    raw_matches: list[dict],
    top_n: int = 3,
    alt: str | None = None,
) -> list[IngredientCandidate]:
    """Re-rank wger's search results against the name Gemini detected.

    wger returns its first matches in no particular order of similarity, so we
    fetch a wide page and re-score locally; the 2-3 options shown to the user
    are the ones that actually read as the same food. When wger already sent
    the nutrition values (ingredientinfo), they travel with the candidate.
    """
    candidates = []
    for score, item in rank_matches(detected_name, raw_matches, top_n, alt=alt):
        energy = item.get("energy")
        candidates.append(
            IngredientCandidate(
                id=item["id"],
                name=item["name"],
                image=item.get("image"),
                score=round(min(score, 100) / 100, 3),
                energy_kcal_100g=float(energy) if energy is not None else None,
            )
        )
    return candidates
