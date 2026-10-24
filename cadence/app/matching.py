from rapidfuzz import fuzz

from .schemas import IngredientCandidate


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace(",", " ").split())


def match_score(wanted: str, candidate: str) -> float:
    """0..100. WRatio finds the words; plain ratio punishes extra words, so
    "Vanilla ice cream" beats "Cherry vanilla ice cream, cherry vanilla"."""
    a, b = _norm(wanted), _norm(candidate)
    return (fuzz.WRatio(a, b) + fuzz.ratio(a, b)) / 2


def rank_matches(wanted: str, raw_matches: list[dict], top_n: int) -> list[tuple[float, dict]]:
    scored = [(match_score(wanted, item["name"]), item) for item in raw_matches]
    # Ties: the shorter (more generic) name first.
    scored.sort(key=lambda pair: (-pair[0], len(pair[1]["name"])))
    return scored[:top_n]


def rank_candidates(
    detected_name: str,
    raw_matches: list[dict],
    top_n: int = 3,
) -> list[IngredientCandidate]:
    """Re-rank wger's search results against the name Gemini detected.

    wger returns its first matches in no particular order of similarity, so we
    fetch a wide page and re-score locally; the 2-3 options shown to the user
    are the ones that actually read as the same food. When wger already sent
    the nutrition values (ingredientinfo), they travel with the candidate.
    """
    candidates = []
    for score, item in rank_matches(detected_name, raw_matches, top_n):
        energy = item.get("energy")
        candidates.append(
            IngredientCandidate(
                id=item["id"],
                name=item["name"],
                image=item.get("image"),
                score=round(score / 100, 3),
                energy_kcal_100g=float(energy) if energy is not None else None,
            )
        )
    return candidates
