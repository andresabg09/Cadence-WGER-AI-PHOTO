import importlib.util
import os
from pathlib import Path


def load_staples():
    os.environ["CADENCE_NO_RUN"] = "1"
    path = Path(__file__).resolve().parents[1] / "scripts" / "seed_staples.py"
    spec = importlib.util.spec_from_file_location("seed_staples", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_staple_values_are_internally_consistent():
    """Catch typos in the hand-entered table: macros must roughly explain the calories."""
    staples = load_staples().STAPLES
    assert len(staples) >= 60
    for en, es, kcal, protein, carbs, fat, fiber in staples:
        assert en and es, (en, es)
        assert protein + carbs + fat <= 100.5, en
        estimated = 4 * protein + 4 * carbs + 9 * fat
        # Atwater estimate is within ~25% for whole foods (alcohol-free, rounding, fiber)
        assert abs(estimated - kcal) <= max(25, 0.25 * kcal), f"{en}: {kcal} kcal vs {estimated:.0f} from macros"
        assert 0 <= fiber <= carbs + 0.01, en


def test_staple_uuids_are_stable_and_unique():
    module = load_staples()
    records = module.staple_records({"en": 2, "es": 4})
    assert len(records) == len(module.STAPLES) * 2
    assert len({r["uuid"] for r in records}) == len(records)
    assert module.staple_uuid("en", "Banana") == module.staple_uuid("en", "banana")
