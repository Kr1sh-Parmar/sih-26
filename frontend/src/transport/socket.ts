/**
 * The real transport. Mirrors mockSocket's `Replay` handle exactly, so a
 * screen swaps one import and nothing else changes.
 *
 * mockSocket stays. It is not dead code: context/DEMO.md keeps a backup path
 * for the day the webcam fails, and the console still has to build without a
 * backend running.
 *
 * The API is on the same box as the console. localhost is the only host this
 * file ever names, which is what keeps scripts/check-offline.sh passing.
 */
import type { Band, ScreeningEvent, Signal } from "../contracts";
import type { FixtureDoc, Replay } from "./mockSocket";

const API =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

const WS = API.replace(/^http/, "ws");

export interface StartedScreening {
  id: string;
  session_id: string;
}

/** POST a capture. The socket does the work; this just claims an id. */
export async function startScreening(
  blob: Blob,
  docType: string,
  sessionId: string,
  opts: { uploaded?: boolean; live?: Blob; liveFrames?: Blob[] } = {},
): Promise<StartedScreening> {
  const body = new FormData();
  body.append("image", blob, "capture.jpg");
  body.append("doc_type", docType);
  body.append("session_id", sessionId);
  body.append("uploaded", String(opts.uploaded ?? false));

  // The camera path also supplies the person. `live` is the single best frame
  // and drives 1:1 matching; `live_frames` is the short burst the blink check
  // reads, appended under one repeated field name because that is what
  // FastAPI binds to `list[UploadFile]`. A file upload sends neither.
  if (opts.live) body.append("live", opts.live, "live.jpg");
  for (const [i, frame] of (opts.liveFrames ?? []).entries()) {
    body.append("live_frames", frame, `burst-${i}.jpg`);
  }

  const response = await fetch(`${API}/screen`, { method: "POST", body });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail ?? "The capture could not be accepted");
  }
  return response.json();
}

/** Replay a fixture through the real fusion engine. The mockSocket stand-in. */
export async function startReplay(
  fixture: string,
  sessionId = "replay",
): Promise<StartedScreening> {
  const body = new FormData();
  body.append("session_id", sessionId);
  const response = await fetch(`${API}/screen/replay/${fixture}`, {
    method: "POST",
    body,
  });
  if (!response.ok) throw new Error(`Unknown fixture ${fixture}`);
  return response.json();
}

/**
 * Stream one screening. Returns the same handle shape as replayFixture, so a
 * screen that unmounts mid-run stops the stream the same way.
 */
export function connect(
  screeningId: string,
  emit: (e: ScreeningEvent) => void,
): Replay {
  const socket = new WebSocket(`${WS}/screen/${screeningId}`);

  socket.onmessage = (message) => {
    try {
      emit(JSON.parse(message.data) as ScreeningEvent);
    } catch {
      // A frame we cannot parse is a bug, not something the officer can act
      // on. Say so rather than leaving the console stuck mid-phase.
      emit({
        type: "error",
        message: "The screening service sent something unreadable.",
        recoverable: false,
      });
    }
  };

  socket.onerror = () =>
    emit({
      type: "error",
      message: "Lost the connection to the screening service.",
      recoverable: true,
    });

  return {
    cancel: () => {
      if (socket.readyState <= WebSocket.OPEN) socket.close();
    },
  };
}

/** The document bundle the event stream does not carry: image, fields, faces. */
export async function fetchDoc(screeningId: string): Promise<FixtureDoc> {
  const response = await fetch(`${API}/screen/${screeningId}/doc`);
  if (!response.ok) throw new Error("This screening has expired");
  return response.json();
}

export function imageUrl(screeningId: string): string {
  return `${API}/screen/${screeningId}/image`;
}

/** True when a backend is reachable. Lets a screen fall back to fixtures. */
export async function isLive(): Promise<boolean> {
  try {
    const response = await fetch(`${API}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

// ------------------------------------------------------------ audit trail

/** One recorded screening. Mirrors screening_events in CONTRACTS.md §8, minus
 *  the columns the console must never render — there is no raw identity
 *  number here because the database does not hold one. */
export interface AuditEvent {
  id: string;
  session_id: string;
  doc_type: string;
  created_at: string;
  band: Band;
  score: number;
  coverage: number;
  id_number_hash: string | null;
  id_number_last4: string | null;
  officer_id: string | null;
  model_versions: Record<string, string | null>;
  signed: boolean;
  signals: Signal[];
}

export interface EventPage {
  total: number;
  limit: number;
  offset: number;
  events: AuditEvent[];
}

export async function fetchEvents(limit = 25, offset = 0): Promise<EventPage> {
  const response = await fetch(`${API}/events?limit=${limit}&offset=${offset}`);
  if (!response.ok) throw new Error("The audit trail could not be read");
  return response.json();
}

export interface RescoreResult {
  event_id: string;
  doc_type: string;
  recorded: { band: Band; score: number; coverage: number };
  rescored: { band: Band; score: number; coverage: number; reason: string | null };
  changed: boolean;
}

/** The operating point a re-score is run under. Band edges from the settings
 *  store, sent as the server names them. */
export interface RescoreBands {
  green_below: number;
  amber_below: number;
  coverage_floor: number;
}

/**
 * Re-score one stored event under a different operating point.
 *
 * The client does not recompute a verdict — it never has and this is the
 * endpoint that keeps that true. Fusion is server-side, and a second scorer in
 * the browser is exactly the thing that drifts and then disagrees with the
 * audit log it is supposed to explain.
 */
export async function rescoreEvent(
  eventId: string,
  bands: RescoreBands,
): Promise<RescoreResult> {
  const response = await fetch(`${API}/rescore`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_id: eventId, bands }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail ?? "That screening could not be re-scored");
  }
  return response.json();
}

/**
 * Re-score a whole page of stored events under one operating point, in one
 * request. Same server, same scorer, same result shape as `rescoreEvent` — the
 * only difference is that the audit table asks once instead of once per row.
 *
 * Two things about the response the caller must respect:
 *
 *  - `results` may be SHORTER than `ids`. An event the server could not
 *    re-score is omitted rather than failing the batch, so results are keyed by
 *    their own `event_id` and never by array position. Keying by position is
 *    how one unreadable event would silently relabel every row beneath it.
 *  - There is a cap on how many ids one request may carry. Over it the server
 *    answers 400 with a `detail` sentence, surfaced here the same way
 *    `rescoreEvent` surfaces one.
 */
export async function rescoreEvents(
  ids: string[],
  bands: RescoreBands,
): Promise<RescoreResult[]> {
  const response = await fetch(`${API}/rescore/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_ids: ids, bands }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail ?? "These screenings could not be re-scored");
  }
  const page = (await response.json()) as { results: RescoreResult[] };
  return page.results;
}

// -------------------------------------------------------------- sessions

/** One field a signed document vouched for, and whether the other agreed.
 *
 *  `from_value` and `to_value` are null once the session has expired: they are
 *  the traveller's own data and are never written to the audit trail, only
 *  held while they are at the counter. The verdict and the evidence sentence
 *  outlive them. */
export interface SessionEdge {
  field: string;
  from: string;
  to: string;
  agrees: boolean;
  trust_class: Signal["trust_class"];
  evidence: string;
  from_value: string | null;
  to_value: string | null;
}

export interface SessionView {
  session_id: string;
  documents: {
    id: string;
    doc_type: string;
    band: Band | null;
    score: number | null;
    coverage: number | null;
    signed: boolean;
    created_at: string;
  }[];
  edges: SessionEdge[];
}

export async function fetchSession(sessionId: string): Promise<SessionView> {
  const response = await fetch(`${API}/sessions/${sessionId}`);
  if (!response.ok) throw new Error("That session could not be read");
  return response.json();
}
