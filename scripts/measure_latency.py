"""Measure screening latency on this machine. BUILD TIME ONLY.

    python scripts/measure_latency.py --runs 30

ROADMAP Phase 5 asks for p50/p95 measured on the actual demo machine, and
DEMO.md's 72-hour checklist requires the number before the panel sees anything.
Quoting TECHNICAL-SPEC section 10's budget table as if it were a measurement is
exactly the kind of claim that gets challenged.

Documents come from `data/generator/`, so this measures the real pipeline on
real inputs rather than on a blank canvas whose emptiness makes every stage
look fast. Nothing here is importable from the screening path.

**p95, not the mean.** A checkpoint queue is served by the slow tail, and a
mean hides it behind the many documents that cleared instantly.
"""
import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2                                                          # noqa: E402

from api import router as pipeline                                  # noqa: E402
from core import registry                                           # noqa: E402
from core.store import Store                                        # noqa: E402

#: TECHNICAL-SPEC.md section 2, the per-layer Tier 1 budget. What we are
#: measured against, not what we claim to have measured.
BUDGET_MS = {
    "decode": 60,
    "extraction": 250,
    "validation": 15,
    "tamper": 160,
    "face": 320,
    "fusion": 10,
}
TIER1_TOTAL_MS = 1020


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))
    return ordered[index]


def report(name: str, values: list[float], budget: float | None = None) -> None:
    p50, p95 = percentile(values, 0.50), percentile(values, 0.95)
    line = (f"  {name:14s} p50 {p50:7.1f} ms   p95 {p95:7.1f} ms   "
            f"max {max(values):7.1f} ms")
    if budget:
        verdict = "over" if p95 > budget else "ok"
        line += f"   budget {budget:5.0f} ms  {verdict.upper()}"
    print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=25)
    parser.add_argument("--doc-type", default="passport")
    parser.add_argument("--warmup", type=int, default=3)
    args = parser.parse_args()

    try:
        from data.generator import build
    except ImportError as exc:
        print(f"the generator needs its build-time deps: {exc}\n"
              f"  pip install -r requirements-build.txt && "
              f"python scripts/fetch_fonts.py")
        return 1

    print("warming models (never inside a request handler)")
    warm = registry.warm()
    print(f"  loaded: {', '.join(warm['loaded']) or 'nothing'}")
    if warm["missing"]:
        print(f"  missing: {', '.join(warm['missing'])}")
        print("  -> stages that need those weights are not being timed; the")
        print("     numbers below are a floor, not the finished system.")

    store = Store(":memory:")
    images = [build(args.doc_type, seed=1000 + n).image
              for n in range(args.warmup + args.runs)]
    encoded = [cv2.imencode(".png", image)[1].tobytes() for image in images]

    stages: dict[str, list[float]] = {k: [] for k in BUDGET_MS}
    totals: list[float] = []

    print(f"\nscreening {args.runs} generated {args.doc_type} documents "
          f"({args.warmup} warmup)")
    for index, raw in enumerate(encoded):
        started = time.perf_counter()
        ctx = pipeline.build_context(raw, args.doc_type, "latency")
        decoded = time.perf_counter()

        # Drained rather than inspected: the per-stage numbers come off the
        # signals, which every module stamps with its own `latency_ms`. That is
        # the unit the budget is written in, and it is what the audit log keeps.
        for _event in pipeline.screen(ctx, store=store, uploaded=True, raw=raw):
            pass
        total = (time.perf_counter() - started) * 1000

        if index < args.warmup:
            continue
        totals.append(total)
        # Per-module time comes off the signals themselves - every module
        # stamps `latency_ms`, which is the number the budget is written in.
        by_module: dict[str, float] = {}
        for signal in ctx.signals:
            by_module[signal.module] = max(by_module.get(signal.module, 0.0),
                                           float(signal.latency_ms))
        for module, value in by_module.items():
            stages.setdefault(module, []).append(value)
        stages["decode"].append((decoded - started) * 1000)

    print("\nper stage, from the latency_ms every module stamps on its signals")
    for name in ("decode", "extraction", "validation", "tamper", "face"):
        if stages.get(name):
            report(name, stages[name], BUDGET_MS.get(name))

    print("\nend to end")
    report("tier 1 total", totals, TIER1_TOTAL_MS)

    p95 = percentile(totals, 0.95)
    print(f"\n  mean {statistics.mean(totals):.1f} ms over {len(totals)} runs")
    print(f"  {'WITHIN' if p95 <= TIER1_TOTAL_MS else 'OVER'} the "
          f"{TIER1_TOTAL_MS} ms Tier 1 budget at p95")
    print("\n  These are clean generated renders on this machine. A scanned,")
    print("  printed document is larger and slower; re-run on the demo box with")
    print("  the documents that will actually be scanned before quoting this.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
