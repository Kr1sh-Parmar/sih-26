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
import type { ScreeningEvent } from "../contracts";
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
  opts: { uploaded?: boolean } = {},
): Promise<StartedScreening> {
  const body = new FormData();
  body.append("image", blob, "capture.jpg");
  body.append("doc_type", docType);
  body.append("session_id", sessionId);
  body.append("uploaded", String(opts.uploaded ?? false));

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
