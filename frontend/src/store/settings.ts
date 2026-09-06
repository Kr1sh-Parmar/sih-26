/**
 * Operator settings. The checkpoint commander sets these, not us
 * (context/DEMO.md Scene 4).
 *
 * Persisted per workstation. A kiosk browser can block storage, so every
 * access is wrapped — a console that will not start because localStorage threw
 * is a worse failure than a forgotten threshold.
 */
import { create } from "zustand";

export interface Settings {
  /** Cosine threshold for 1:1 document-to-live face verification. */
  faceThreshold: number;
  /** Half-width of the review band either side of the threshold. */
  reviewBand: number;
  /** Below this weighted coverage the verdict is AMBER, never GREEN. */
  coverageFloor: number;
  /** Band edges from config/bands.yaml. */
  amberAt: number;
  redAt: number;
  /** Crossings per day, used to turn a rate into a number of people. */
  dailyVolume: number;

  set: (patch: Partial<Omit<Settings, "set" | "reset">>) => void;
  reset: () => void;
}

const DEFAULTS = {
  faceThreshold: 0.32,
  reviewBand: 0.06,
  coverageFloor: 0.7,
  amberAt: 0.2,
  redAt: 0.6,
  dailyVolume: 5000,
};

const KEY = "ssb.console.settings";

function load(): typeof DEFAULTS {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS;
  } catch {
    return DEFAULTS;
  }
}

function save(s: typeof DEFAULTS) {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* kiosk browsers block storage; the session still works */
  }
}

export const useSettings = create<Settings>((set, get) => ({
  ...load(),
  set: (patch) => {
    set(patch);
    const { set: _s, reset: _r, ...rest } = get();
    save(rest as typeof DEFAULTS);
  },
  reset: () => {
    set(DEFAULTS);
    save(DEFAULTS);
  },
}));
