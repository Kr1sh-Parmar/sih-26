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
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { ModuleName, ScreeningEvent } from "../contracts";
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
  const startedAt = useRef<number>(0);
  /** Real, client-timestamped arrival time (ms since `startedAt`) of each
   *  module's first signal, and of the final `done` phase — the only
   *  timing data the stepper can honestly show. See StreamStatus.tsx for
   *  why this lives here rather than inside the component: `onEvent` below
   *  already sees every event exactly once, in real arrival order. */
  const stageTimes = useRef<Partial<Record<ModuleName | "done", number>>>({});
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
   *  fallback is not vestigial — it is the backup path for the day the webcam
   *  fails in front of the panel. */
  const signedRef = useRef(false);
  const screeningId = useRef<string | null>(null);
  /** URL of the real capture, once the backend has claimed an id for it.
   *  Null for a replayed fixture, which has no image to serve. */
  const [captureImage, setCaptureImage] = useState<string | null>(null);
  const takeCapture = useCapture((c) => c.take);
  const captureRef = useRef<PendingCapture | null | undefined>(undefined);
  if (captureRef.current === undefined) captureRef.current = takeCapture();
  const capture = captureRef.current;

  // The traveller's own photograph, still in the browser from before it was
  // uploaded. The backend never stores or returns this crop (CLAUDE.md — no
  // raw biometric outlives the session), so it is the only copy that will
  // ever exist, and it is gone the moment this screen unmounts.
  const liveImageSrc = useMemo(
    () => (capture?.live ? URL.createObjectURL(capture.live) : null),
    [capture],
  );
  useEffect(() => () => { if (liveImageSrc) URL.revokeObjectURL(liveImageSrc); }, [liveImageSrc]);

  // The document's own face box, straight off the signal that located it —
  // the same field DocumentViewer already draws its overlay boxes from.
  const docFaceRegion = useMemo(
    () =>
      s.signals.find((sig) => sig.id === "face.match.cosine")?.region ??
      s.signals.find((sig) => sig.id === "face.doc.quality")?.region ??
      null,
    [s.signals],
  );

  // `/screen/{id}/doc` always reports `face.cosine: null` — it answers before
  // the pipeline has run, so it cannot know the value yet, and nothing
  // re-fetches it afterwards. The only place the real number ever reaches the
  // browser for a live capture is this signal's own evidence sentence
  // ("...match at cosine 0.40..."), so this is a fallback, not the primary
  // path — a replayed fixture already carries `doc.face.cosine` directly.
  const liveCosine = useMemo(() => {
    const evidence = s.signals.find((sig) => sig.id === "face.match.cosine")?.evidence;
    const match = evidence?.match(/cosine (-?\d+\.\d+)/);
    return match ? Number(match[1]) : null;
  }, [s.signals]);

  useEffect(() => {
    if (mode === "probing") return;

    s.reset();
    startedAt.current = performance.now();
    stageTimes.current = {};
    signedRef.current = false;
    screeningId.current = null;
    setCaptureImage(null);

    const onEvent = (e: ScreeningEvent) => {
      s.apply(e);
      if (e.type === "signal" && stageTimes.current[e.signal.module] === undefined) {
        stageTimes.current[e.signal.module] = performance.now() - startedAt.current;
      }
      if (e.type === "phase" && e.phase === "done" && stageTimes.current.done === undefined) {
        stageTimes.current.done = performance.now() - startedAt.current;
      }
      // A screened capture joins the session, so the next document is visibly
      // checked against it and the session view has something to draw. The
      // backend already remembers it either way — this is the console catching
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
    // stream starts on this tick. A real capture cannot take this path —
    // there is no backend to screen it — so it reports that rather than
    // quietly showing the officer a fixture verdict for a document they just
    // captured.
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
        // demo scenes. Same socket, same fusion engine, same event contract —
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
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-8 px-6 py-6 lg:grid-cols-[minmax(0,2fr)_minmax(26rem,1fr)]">
      {/* ---------------------------------------------- physical evidence */}
      <div className="min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <StreamStatus
            phase={s.phase}
            signals={s.signals}
            stageTimes={stageTimes.current}
            runStartedAt={startedAt.current}
          />
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
            cosine={doc?.face.cosine ?? liveCosine}
            threshold={doc?.face.threshold ?? 0.32}
            docImageSrc={captureImage}
            docRegion={docFaceRegion}
            docCanvas={canvas}
            liveImageSrc={liveImageSrc}
          />
          <FieldTable fields={doc?.fields ?? []} />
        </div>
      </div>

      {/* ------------------------------------------------ written record */}
      <div className="min-w-0 space-y-5">
        <VerdictBand band={s.band} score={s.score} coverage={s.coverage} />

        <div
          className="rounded-[var(--radius-lg)] border border-iris/40 bg-white p-6"
          style={{ boxShadow: "var(--shadow-sm)" }}
        >
          <h2 className="text-[length:var(--text-evidence)] font-semibold">Evidence</h2>
          <div className="mt-1 h-px bg-iris/60" />
          <EvidenceList findings={s.findings} signals={s.signals} />
        </div>

        <DisclosureNotice text={s.disclosure} />

        {/* Scene picker. Hidden while a real capture is on screen — not
            cosmetic: the effect that screens a document is keyed on `scene`,
            so a click here would re-POST the officer's capture and bill a
            second screening for one traveller. It stays for the rehearsed
            running order, and for the day the camera fails in front of the
            panel. */}
        <div className="rounded-[var(--radius-lg)] border border-iris/30 bg-bloom/30 p-5">
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
                      "rounded-[var(--radius-md)] border px-3 py-1.5 text-label font-medium transition-all",
                      scene === sc.key
                        ? "border-guilloche bg-guilloche/10 text-guilloche"
                        : "border-iris/60 text-iris-ink hover:border-iris-ink hover:bg-bloom",
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
