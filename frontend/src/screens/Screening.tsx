/**
 * The screening screen.
 *
 * Left is the physical evidence — the document under glass, the face pair, the
 * extracted fields. Right is the written record — verdict, then the ordered
 * evidence. That is the order the officer actually works in: look at the
 * document, then read the finding.
 *
 * Every panel reserves its space before anything streams in. Layout shift at
 * 450 ms is what makes a fast system feel slow.
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { ScreeningEvent } from "../contracts";
import { useScreening } from "../store/screening";
import { fixture, replayFixture, type FixtureName } from "../transport/mockSocket";
import { connect, fetchDoc, imageUrl, startReplay, startScreening } from "../transport/socket";
import { useCapture, type PendingCapture } from "../store/capture";
import { useSession } from "../store/session";
import { useMode } from "../transport/mode";
import { docLabel } from "../domain/docType";
import { ModeBadge } from "../components/ModeBadge";
import { VerdictBand } from "../components/VerdictBand";
import { EvidenceList } from "../components/EvidenceList";
import { DisclosureNotice } from "../components/DisclosureNotice";
import { DocumentViewer } from "../components/DocumentViewer";
import { FieldTable } from "../components/FieldTable";
import { FacePair } from "../components/FacePair";
import { StreamStatus } from "../components/StreamStatus";
import { cn } from "../lib/utils";

const SCENES: { key: FixtureName; label: string }[] = [
  { key: "green", label: "Clean passport" },
  { key: "red", label: "Altered date of birth" },
  { key: "crossdoc", label: "PAN against a signed Aadhaar" },
  { key: "amber", label: "Capture too soft" },
];

export function Screening() {
  const [scene, setScene] = useState<FixtureName>("green");
  const [elapsed, setElapsed] = useState<number | null>(null);
  const startedAt = useRef<number>(0);
  const mode = useMode();

  const s = useScreening();
  const navigate = useNavigate();
  const sessionId = useSession((x) => x.sessionId);
  const addToSession = useSession((x) => x.add);

  /** A capture arriving from the Capture screen, read exactly once.
   *
   *  `take()` clears the store, and the result is parked in a ref rather than
   *  in state so that a re-render cannot re-consume it. When this is null the
   *  screen behaves exactly as it always has: the scene buttons drive it. That
   *  fallback is not vestigial - DEMO.md keeps the fixtures as the backup path
   *  for the day the webcam fails in front of the panel. */
  /** Whether this document's own signature verified, for the session list.
   *  A ref because it is set by one event and read by a later one inside the
   *  same handler - state would not have landed in time. */
  const signedRef = useRef(false);
  const screeningId = useRef<string | null>(null);
  /** URL of the real capture, once the backend has claimed an id for it.
   *  Null for a replayed fixture, which has no image to serve. */
  const [captureImage, setCaptureImage] = useState<string | null>(null);
  const takeCapture = useCapture((c) => c.take);
  const captureRef = useRef<PendingCapture | null | undefined>(undefined);
  if (captureRef.current === undefined) captureRef.current = takeCapture();
  const capture = captureRef.current;

  useEffect(() => {
    if (mode === "probing") return;

    s.reset();
    startedAt.current = performance.now();
    setElapsed(null);
    signedRef.current = false;
    screeningId.current = null;
    setCaptureImage(null);

    const onEvent = (e: ScreeningEvent) => {
      s.apply(e);
      if (e.type === "phase" && e.phase === "done") {
        setElapsed(Math.round(performance.now() - startedAt.current));
      }
      // A screened capture joins the session, so the next document is visibly
      // checked against it and the session view has something to draw. The
      // backend already remembers it either way - this is the console catching
      // up with what the service did, not a second source of truth.
      if (e.type === "verdict" && capture) {
        addToSession({
          id: screeningId.current ?? capture.docType,
          docType: capture.docType,
          label: docLabel(capture.docType),
          signed: signedRef.current,
          band: e.band,
          fixture: "green",
        });
      }
      if (e.type === "signal" && e.signal.id === "validation.signature.valid"
          && e.signal.verdict === "pass") {
        signedRef.current = true;
      }
    };

    // Fixtures: the same scene, replayed locally. Nothing to await, so the
    // stream starts on this tick. A real capture cannot take this path - there
    // is no backend to screen it - so it reports that rather than quietly
    // showing the officer a fixture verdict for a document they just captured.
    if (mode === "fixtures") {
      if (capture) {
        s.apply({
          type: "error",
          message:
            "This capture cannot be screened - the screening service is not " +
            "reachable, and the scenes below are recorded fixtures, not this " +
            "document.",
          recoverable: true,
        });
        return;
      }
      s.setDoc(fixture(scene));
      const run = replayFixture(scene, onEvent);
      return () => run.cancel();
    }

    // Live: the same fixture signals, but scored by the production fusion
    // engine server-side. Two awaits where there was one synchronous call, so
    // the socket may open after this effect has already been torn down.
    let cancel: (() => void) | null = null;
    let dead = false;

    (async () => {
      try {
        // A document the officer actually captured takes precedence over the
        // demo scenes. Same socket, same fusion engine, same event contract -
        // the only difference is which endpoint claimed the id.
        const started = capture
          ? await startScreening(capture.blob, capture.docType, sessionId, {
              uploaded: capture.uploaded,
              live: capture.live,
              liveFrames: capture.liveFrames,
            })
          : await startReplay(scene);
        screeningId.current = started.id;
        const doc = await fetchDoc(started.id);
        if (dead) return;
        if (capture) setCaptureImage(imageUrl(started.id));
        s.setDoc(doc);
        cancel = connect(started.id, onEvent).cancel;
      } catch (error) {
        if (dead) return;
        // Falling back silently would be the dangerous outcome: the officer
        // would see a verdict and have no way to know it came from a local
        // fixture instead of the service.
        s.apply({
          type: "error",
          message:
            error instanceof Error
              ? error.message
              : "The screening service could not be reached.",
          recoverable: true,
        });
      }
    })();

    return () => {
      dead = true;
      cancel?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene, mode, capture]);

  const doc = s.doc;
  const canvas = (doc?.meta.canvas as [number, number]) ?? [1654, 1170];

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-8 px-8 py-6 lg:grid-cols-[minmax(0,2fr)_minmax(26rem,1fr)]">
      {/* ---------------------------------------------- physical evidence */}
      <div className="min-w-0">
        <div className="flex items-center justify-between gap-4">
          <StreamStatus phase={s.phase} signals={s.signals} elapsedMs={elapsed} />
          <ModeBadge mode={mode} />
        </div>

        <div className="mt-4">
          {doc && (
            <DocumentViewer
              docType={doc.meta.doc_type}
              canvas={canvas}
              fields={doc.fields}
              signals={s.signals}
              imageSrc={captureImage}
            />
          )}
        </div>

        <div className="grid gap-8 md:grid-cols-2">
          <FacePair
            cosine={doc?.face.cosine ?? null}
            threshold={doc?.face.threshold ?? 0.32}
          />
          <FieldTable fields={doc?.fields ?? []} />
        </div>
      </div>

      {/* ------------------------------------------------ written record */}
      <div className="min-w-0 bg-bloom/40 p-6">
        <VerdictBand band={s.band} score={s.score} coverage={s.coverage} />

        <h2 className="mt-8 text-[length:var(--text-evidence)]">Evidence</h2>
        <div className="mt-1 border-t border-intaglio" />

        <EvidenceList findings={s.findings} signals={s.signals} />

        <DisclosureNotice text={s.disclosure} />

        {/* Scene picker, and it is hidden while a real capture is on screen.
            Not cosmetic: the effect that screens a document is keyed on
            `scene`, so a click here would re-POST the officer's capture and
            bill a second screening for one traveller. It stays for the
            rehearsed running order DEMO.md wants, and for the day the camera
            fails in front of the panel. */}
        <div className="mt-10 border-t border-iris pt-4">
          {capture ? (
            <p className="text-label text-iris-ink">
              Screening the {capture.source === "camera" ? "camera" : capture.source}{" "}
              capture taken at the counter.{" "}
              <button
                type="button"
                onClick={() => navigate("/capture")}
                className="underline underline-offset-2 hover:text-intaglio"
              >
                Capture another document
              </button>
            </p>
          ) : (
            <>
          <p className="text-label text-iris-ink">
            {mode === "live"
              ? "Replay a rehearsed case through the live fusion engine"
              : "Replay a rehearsed case"}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {SCENES.map((sc) => (
              <button
                key={sc.key}
                type="button"
                onClick={() => setScene(sc.key)}
                className={cn(
                  "border px-3 py-1.5 text-label transition-colors",
                  scene === sc.key
                    ? "border-intaglio bg-intaglio text-paper"
                    : "border-iris text-iris-ink hover:bg-bloom",
                )}
              >
                {sc.label}
              </button>
            ))}
          </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
