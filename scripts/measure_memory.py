"""Measure the resident memory ceiling with every model warm. BUILD TIME ONLY.

    python scripts/measure_memory.py
    python scripts/measure_memory.py --runs 3 --doc-types passport,aadhaar,pan

ROADMAP Phase 5 asks for the memory ceiling with all sessions warm, and DEMO.md
answers "Why not use a GPU?" with "the whole system runs in under 500 MB warm".
That sentence is a claim a judge can test in ten seconds with Task Manager, so
it needs a measurement behind it rather than an estimate.

Nothing here is importable from the screening path, same rule as
`measure_latency.py`. It deliberately measures in one process, in the order the
real process does it: interpreter, then imports, then `registry.warm()`, then
real documents - because the interesting number is not any one of those, it is
where the curve stops rising.

**No new dependency.** `psutil` is not in `requirements.txt`, so this reads the
OS counters directly: `GetProcessMemoryInfo` on Windows, `/proc/self/status` on
Linux (which is what the Docker image is). Adding a package to measure the
footprint of a package would be its own joke.
"""
import argparse
import ctypes
import gc
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: The claim in DEMO.md's question table. Measured against, not assumed.
CLAIM_MB = 500


def _windows_counters() -> tuple[float, float]:
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_uint32),
                    ("PageFaultCount", ctypes.c_uint32),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]

    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    # restype matters: GetCurrentProcess returns the pseudo-handle (HANDLE)-1,
    # and ctypes' default c_int truncates it on 64-bit, which the API then
    # rejects with ERROR_INVALID_HANDLE.
    current = ctypes.windll.kernel32.GetCurrentProcess
    current.restype = ctypes.c_void_p
    if not ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.c_void_p(current()), ctypes.byref(counters), counters.cb):
        raise OSError(ctypes.GetLastError(), "GetProcessMemoryInfo failed")
    return (counters.WorkingSetSize / 1e6, counters.PeakWorkingSetSize / 1e6)


def _linux_counters() -> tuple[float, float]:
    # VmHWM is the high-water mark, the equivalent of PeakWorkingSetSize.
    fields = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(("VmRSS:", "VmHWM:")):
            key, value, _unit = line.split()
            fields[key.rstrip(":")] = float(value) / 1000  # kB -> MB
    return fields.get("VmRSS", 0.0), fields.get("VmHWM", 0.0)


def rss() -> tuple[float, float]:
    """(resident MB, peak resident MB) for this process, from the OS."""
    gc.collect()
    if sys.platform == "win32":
        return _windows_counters()
    if sys.platform.startswith("linux"):
        return _linux_counters()
    # ponytail: macOS is not a deployment target - the image is Debian and the
    # demo box is Windows. ru_maxrss is peak only, which is enough to not lie.
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    return peak, peak


def step(label: str, baseline: float) -> float:
    now, peak = rss()
    print(f"  {label:34s} {now:7.1f} MB   (+{now - baseline:6.1f})"
          f"   peak {peak:7.1f} MB")
    return now


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=2,
                        help="documents screened per type")
    parser.add_argument("--doc-types", default="passport,aadhaar,pan")
    parser.add_argument("--seed", type=int, default=2000)
    args = parser.parse_args()
    doc_types = [t.strip() for t in args.doc_types.split(",") if t.strip()]

    print("resident memory, one process, in the order the real one does it\n")
    start, _ = rss()
    print(f"  {'bare interpreter':34s} {start:7.1f} MB")

    import cv2                                                    # noqa: F401
    from api import router as pipeline
    from core import registry
    from core.store import Store
    step("+ imports (onnxruntime, cv2, api)", start)

    # Exactly what api/main.py's lifespan does, and the only place sessions are
    # built. If this number is the ceiling, the claim holds.
    warm = registry.warm()
    print(f"\n  loaded:  {', '.join(warm['loaded']) or 'nothing'}")
    if warm["missing"]:
        print(f"  missing: {', '.join(warm['missing'])}  <- not resident, so "
              f"not counted below")
    print()
    idle = step("warm and idle (registry.warm())", start)

    try:
        from data.generator import build
    except ImportError as exc:
        print(f"\nthe generator needs its build-time deps: {exc}")
        print("  pip install -r requirements-build.txt && "
              "python scripts/fetch_fonts.py")
        return 1

    store = Store(":memory:")
    working = idle
    for doc_type in doc_types:
        vlm = 0
        for n in range(args.runs):
            image = build(doc_type, seed=args.seed + n).image
            raw = cv2.imencode(".png", image)[1].tobytes()
            ctx = pipeline.build_context(raw, doc_type, "memory")
            for _event in pipeline.screen(ctx, store=store, uploaded=True,
                                          raw=raw):
                pass
            # Florence-2 is the whole story in this number, so say how many of
            # these documents actually loaded it rather than leaving the reader
            # to guess which population the figure belongs to.
            vlm += any(s.id.startswith("extraction.vlm")
                       and s.verdict != "not_applicable" for s in ctx.signals)
        working = step(f"warm and working ({doc_type}, VLM {vlm}/{args.runs})",
                       start)

    peak = rss()[1]
    print(f"\n  warm and idle     {idle:7.1f} MB")
    print(f"  warm and working  {working:7.1f} MB")
    print(f"  peak              {peak:7.1f} MB")

    # Three numbers, not one, because "under 500 MB warm" is true of the
    # steady-state resident set and false of the high-water mark, and a judge
    # with Task Manager open sees the high-water mark.
    print(f"\n  against DEMO.md's \"under {CLAIM_MB} MB warm\":")
    for label, value in (("steady, idle", idle), ("steady, working", working),
                         ("high-water mark", peak)):
        print(f"    {label:18s} {value:7.1f} MB  "
              f"{'under' if value <= CLAIM_MB else 'OVER'}")
    print("\n  Read this with the same caveat as the latency number: the field")
    print("  detector is not deployed, so its session is not resident, and")
    print("  Florence-2 is loaded lazily rather than by warm() - it is resident")
    print("  above only if a document above actually fell through to it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
