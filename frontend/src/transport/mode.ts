/**
 * Live backend, or local fixtures?
 *
 * DEMO.md keeps a fixture path deliberately: the webcam fails on the day, the
 * scanner is not at the venue, the API is not up yet. `POST /screen/replay`
 * runs those same fixtures through the *real* fusion engine, so falling back
 * loses the capture, not the scoring.
 *
 * The one thing that must never happen is an officer not knowing which they
 * are looking at. Every screen that can fall back renders `ModeBadge`, and the
 * badge is not decoration — a fixture verdict presented as a real screening is
 * the worst failure this console has.
 *
 * Probed once per page load, not per render. A checkpoint box does not gain or
 * lose its own backend mid-shift, and a health check on every mount is a
 * request storm for no information.
 */
import { useEffect, useState } from "react";
import { isLive } from "./socket";

export type Mode = "probing" | "live" | "fixtures";

let cached: Promise<boolean> | null = null;

function probe(): Promise<boolean> {
  cached ??= isLive();
  return cached;
}

/** Forget the probe. Only for tests — nothing in the UI re-probes. */
export function resetMode(): void {
  cached = null;
}

export function useMode(): Mode {
  const [mode, setMode] = useState<Mode>("probing");

  useEffect(() => {
    let alive = true;
    probe().then((live) => {
      if (alive) setMode(live ? "live" : "fixtures");
    });
    return () => {
      alive = false;
    };
  }, []);

  return mode;
}
