from rapidfuzz import fuzz, process

from .schemas import IngredientCandidate


def rank_candidates(
    detected_name: str,
    raw_matches: list[dict],
    top_n: int = 3,
) -> list[IngredientCandidate]:
    """Re-rank wger's own search results against the name Gemini detected.

    wger's /api/v2/ingredient/search/ already does some server-side
    matching, but it's optimized for human typing, not for a possibly
    verbose/translated name coming out of a vision model. We fetch its
    results and re-score them locally so the 2-3 options we show the user
    are the ones that actually read as the same food.
    """
    if not raw_matches:
        return []

    names = [item["name"] for item in raw_matches]
    scored = process.extract(
        detected_name,
        names,
        scorer=fuzz.WRatio,
        limit=top_n,
    )

    candidates = []
    for name, score, index in scored:
        item = raw_matches[index]
        candidates.append(
            IngredientCandidate(
                id=item["id"],
                name=item["name"],
                image=item.get("image"),
                score=round(score / 100, 3),
            )
        )
    return candidates
