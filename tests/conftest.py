import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: One source of truth. frontend/scripts/build_fixtures.py generates these and
#: the console replays the same bytes, so a fixture that scores wrong here is a
#: fixture the officer console is also showing wrong.
FIXTURE_DIR = ROOT / "frontend" / "src" / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def fixtures() -> dict:
    return {
        "green": load_fixture("signals_green"),
        "red": load_fixture("signals_red_hardfail"),
        "amber": load_fixture("signals_amber_coverage"),
        "crossdoc": load_fixture("signals_crossdoc_mismatch"),
    }


# --------------------------------------------------------------- what is here
#
# The suite runs in two places with deliberately different contents: a developer
# checkout, and the screening image (`docker compose --profile verify run --rm
# verify`), where `.dockerignore` withholds the build-time dependency set, the
# React tree and `data/processed/`. A test whose *inputs* are absent by design
# must skip and say so - if it fails instead, the noise buries the one failure
# that means the image is broken. That is not hypothetical: the run that first
# exercised the image returned 24 failures, of which exactly one was a real bug.
#
# These guards name the missing thing, so the skip reason is a fact about the
# environment rather than "needs deps".

def _importable(module: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


#: The generator's dependencies. Present in a checkout, withheld from the image
#: on purpose - Pillow and Faker have no business in a screening container.
HAVE_GENERATOR_DEPS = _importable("faker") and _importable("PIL")

#: The console's TypeScript sources, which the contract-parity tests read to
#: check that the Python and TypeScript vocabularies agree. Present in a
#: checkout; whether they reach the screening image depends on how narrowly
#: `.dockerignore` re-includes `frontend/` - see the note there.
TS_CONTRACTS = ROOT / "frontend" / "src" / "contracts"

#: The field-detector dataset. Excluded from the image - it is training data,
#: not something the screening path reads.
FIELD_DATASET = ROOT / "data" / "processed" / "fields" / "data.yaml"

needs_generator_deps = pytest.mark.skipif(
    not HAVE_GENERATOR_DEPS,
    reason="the generator's build-time dependencies are not installed here "
           "(deliberate in the screening image): "
           "pip install -r requirements-build.txt")

needs_ts_contracts = pytest.mark.skipif(
    not (TS_CONTRACTS / "signal.ts").exists(),
    reason="frontend/src/contracts is not in this tree; the console has its "
           "own image and this check needs its TypeScript sources")

needs_field_dataset = pytest.mark.skipif(
    not FIELD_DATASET.exists(),
    reason="data/processed/fields is training data and is not in the image")
