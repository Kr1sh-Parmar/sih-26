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
