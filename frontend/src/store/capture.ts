/**
 * The capture waiting to be screened.
 *
 * Capture and Screening are two routes, so the bytes the officer just took
 * have to survive one navigation. They are held here rather than in
 * `session.ts` on purpose: `session.ts` models the audit-trail side of a
 * session — which documents were screened, what vouched for what — and a
 * transient Blob handed between two screens is not that.
 *
 * **Consumed exactly once.** `take()` returns the capture and clears it in the
 * same call, so a back-navigation to Screening cannot silently re-screen the
 * previous traveller's document. That is the failure this shape exists to
 * prevent; an officer seeing a stale verdict attached to the person in front
 * of them is worse than seeing nothing.
 */
import { create } from "zustand";
import type { CaptureSource } from "../domain/quality";

export interface PendingCapture {
  /** The document image. */
  blob: Blob;
  docType: string;
  source: CaptureSource;
  /** Scanner and file uploads set this; it turns on the metadata checks that
   *  are skipped when the scanner wrote the file itself (CLAUDE.md). */
  uploaded: boolean;
  /** The single best live frame, for 1:1 matching. Camera path only. */
  live?: Blob;
  /** The short burst the blink check reads. Camera path only. */
  liveFrames?: Blob[];
}

interface CaptureState {
  pending: PendingCapture | null;
  put: (capture: PendingCapture) => void;
  /** Read and clear. Returns null when there is nothing waiting, which is the
   *  normal case for the fixture-driven demo scenes. */
  take: () => PendingCapture | null;
}

export const useCapture = create<CaptureState>((set, get) => ({
  pending: null,
  put: (pending) => set({ pending }),
  take: () => {
    const { pending } = get();
    if (pending) set({ pending: null });
    return pending;
  },
}));
