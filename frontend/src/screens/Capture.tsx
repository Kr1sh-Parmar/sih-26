/**
 * Capture.
 *
 * Three sources, because a border post may have any of them: a flatbed
 * scanner, a file handed over on a stick, or a webcam pointed at the counter.
 * The webcam path also supplies the live face for 1:1 verification, taken as
 * a guided second step once the document itself is accepted.
 *
 * Quality is graded before submission. The point is to catch a soft capture
 * while the traveller is still standing there, rather than returning an AMBER
 * "re-capture required" after they have moved on.
 */
import { useCallback, useEffect, useRef, useState, type ComponentType } from "react";
import { useNavigate } from "react-router-dom";
import {
  gradeCapture,
  isSubmittable,
  measure,
  type CaptureSource,
  type QualityGate,
  type QualityReading,
} from "../domain/quality";
import { useSession } from "../store/session";
import { useCapture } from "../store/capture";
import { DOC_TYPES, docLabel } from "../domain/docType";
import {
  CameraIcon,
  CheckIcon,
  CrossIcon,
  RetakeIcon,
  ScannerIcon,
  ShutterIcon,
  UploadIcon,
} from "../components/marks/Icon";
import type { MarkProps } from "../components/marks/TrustMark";
import { cn } from "../lib/utils";

/** Frames in the liveness burst, and the gap between them.
 *
 *  Five frames over ~1.4 s. A blink lasts 100-400 ms, so this is wide enough
 *  to contain one and short enough that the traveller is not asked to hold
 *  still. `modules/face/liveness.py` needs at least four to answer at all. */
const BURST_FRAMES = 5;
const BURST_GAP_MS = 280;

const SOURCES: { key: CaptureSource; label: string; hint: string; Icon: ComponentType<MarkProps> }[] = [
  { key: "scanner", label: "Scanner", hint: "Flatbed at the counter", Icon: ScannerIcon },
  { key: "upload", label: "File upload", hint: "Image or scanned PDF", Icon: UploadIcon },
  { key: "camera", label: "Camera", hint: "Also captures live face", Icon: CameraIcon },
];

function GateRow({ gate }: { gate: QualityGate }) {
  return (
    <li className="flex items-start gap-3 py-3.5 border-t border-iris/30 first:border-t-0">
      <span
        className={cn(
          "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-white",
          gate.ok ? "bg-emerald-500" : "bg-red-500",
        )}
      >
        {gate.ok ? <CheckIcon size={11} /> : <CrossIcon size={11} />}
      </span>
      <span className="min-w-0">
        <span className="block font-medium text-[length:var(--text-body)]">{gate.label}</span>
        <span className={cn("mt-0.5 block text-label", gate.ok ? "text-iris-ink" : "text-red-600")}>
          {gate.detail}
        </span>
      </span>
    </li>
  );
}

export function Capture() {
  const navigate = useNavigate();
  const startSession = useSession((s) => s.start);
  const sessionId = useSession((s) => s.sessionId);
  const documents = useSession((s) => s.documents);

  const [source, setSource] = useState<CaptureSource>("upload");
  const [docType, setDocType] = useState<string>("aadhaar");
  const [preview, setPreview] = useState<string | null>(null);
  const [reading, setReading] = useState<QualityReading | null>(null);
  const [busy, setBusy] = useState(false);
  /** Whether the traveller has been photographed separately from the card.
   *  Without it the screening still runs - the face comparison reports
   *  `inconclusive`, which is honest - so this gates the label, not submit. */
  const [liveTaken, setLiveTaken] = useState(false);
  /** The officer said this traveller is not being photographed. Explicit,
   *  because the alternative - a face check that quietly did not run - is the
   *  failure this whole system is built to avoid. */
  const [faceSkipped, setFaceSkipped] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);

  const putCapture = useCapture((c) => c.put);
  /** The bytes themselves, kept out of React state - a Blob does not belong in
   *  a render cycle and nothing re-renders when it changes. */
  const blobRef = useRef<Blob | null>(null);
  const liveRef = useRef<Blob | null>(null);
  const burstRef = useRef<Blob[]>([]);

  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // The camera used for the *traveller*, a different camera from the one that
  // may have taken the document. The document goes on the glass and the
  // person is photographed separately; those are two captures whatever
  // hardware takes them.
  const faceVideoRef = useRef<HTMLVideoElement>(null);
  const faceStreamRef = useRef<MediaStream | null>(null);

  const gates = reading ? gradeCapture(reading, source) : [];
  const documentReady = gates.length > 0 && isSubmittable(gates);
  const passCount = gates.filter((g) => g.ok).length;

  //  Step two opens itself as soon as the document is accepted. The officer is
  //  *asked* for the face rather than having to find a button for it - a check
  //  nobody was prompted to run is a check that does not happen.
  const askingForFace = documentReady && !liveTaken && !faceSkipped;
  const canSubmit = documentReady && !busy && !askingForFace;

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => stopCamera, [stopCamera]);

  useEffect(() => {
    if (source !== "camera") { stopCamera(); return; }
    let cancelled = false;
    setCameraError(null);
    navigator.mediaDevices
      ?.getUserMedia({ video: { width: 1280, height: 720 } })
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) { videoRef.current.srcObject = stream; void videoRef.current.play(); }
      })
      .catch(() => {
        if (!cancelled) setCameraError("No camera available. Use a file or the scanner instead — screening works the same way.");
      });
    return () => { cancelled = true; stopCamera(); };
  }, [source, stopCamera]);

  const stopFaceCamera = useCallback(() => {
    faceStreamRef.current?.getTracks().forEach((t) => t.stop());
    faceStreamRef.current = null;
  }, []);

  useEffect(() => stopFaceCamera, [stopFaceCamera]);

  /** Open the camera for step two, and close it the moment step two is over.
   *  Separate stream from the document camera: the two are never on at once,
   *  and sharing one `srcObject` across two elements loses the stream when
   *  React moves the node. */
  useEffect(() => {
    if (!askingForFace) { stopFaceCamera(); return; }
    let cancelled = false;
    navigator.mediaDevices
      ?.getUserMedia({ video: { width: 1280, height: 720 } })
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        faceStreamRef.current = stream;
        if (faceVideoRef.current) { faceVideoRef.current.srcObject = stream; void faceVideoRef.current.play(); }
      })
      .catch(() => {
        if (!cancelled) {
          setCameraError("No camera available for the live face. Screen the document without it — the face comparison will report that it could not run.");
        }
      });
    return () => { cancelled = true; stopFaceCamera(); };
  }, [askingForFace, stopFaceCamera]);

  function acceptImage(img: HTMLImageElement | HTMLVideoElement, w: number, h: number, url: string) {
    setReading(measure(img, w, h));
    setPreview(url);
  }

  function resetCapture() {
    setPreview(null);
    setReading(null);
    blobRef.current = null;
    liveRef.current = null;
    burstRef.current = [];
    setLiveTaken(false);
    setFaceSkipped(false);
  }

  function onFile(file: File | undefined) {
    if (!file) return;
    blobRef.current = file;
    liveRef.current = null;
    burstRef.current = [];
    setLiveTaken(false);
    setFaceSkipped(false);
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => acceptImage(img, img.naturalWidth, img.naturalHeight, url);
    img.onerror = () => URL.revokeObjectURL(url);
    img.src = url;
  }

  /** One JPEG from a video element, at full sensor resolution. */
  function frameBlob(quality = 0.92, element?: HTMLVideoElement | null): Promise<Blob | null> {
    const v = element ?? videoRef.current;
    if (!v || !v.videoWidth) return Promise.resolve(null);
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext("2d")!.drawImage(v, 0, 0);
    return new Promise((resolve) => canvas.toBlob((b) => resolve(b), "image/jpeg", quality));
  }

  /** The document frame. Only the document. */
  async function grabFrame() {
    const v = videoRef.current;
    if (!v || !v.videoWidth || busy) return;
    setBusy(true);
    try {
      const doc = await frameBlob(0.92, v);
      if (!doc) return;
      blobRef.current = doc;
      acceptImage(v, v.videoWidth, v.videoHeight, URL.createObjectURL(doc));
    } finally {
      setBusy(false);
    }
  }

  /** The traveller. A **separate** photograph, and that is the whole point —
   *  reusing the document frame would compare a face to itself. The burst for
   *  the blink check rides on this action, not the document one, for the same
   *  reason: it has to be frames of a face, not of a card. */
  async function grabLive() {
    const v = faceVideoRef.current;
    if (!v || !v.videoWidth || busy) return;
    setBusy(true);
    try {
      const live = await frameBlob(0.92, v);
      if (!live) return;
      liveRef.current = live;

      const burst: Blob[] = [];
      for (let i = 0; i < BURST_FRAMES; i++) {
        // Lower quality: read for whether the eyes are open, never for a
        // field value, and five full-quality frames is a slow upload on a
        // checkpoint's connection.
        const f = await frameBlob(0.7, v);
        if (f) burst.push(f);
        if (i < BURST_FRAMES - 1) await new Promise((r) => setTimeout(r, BURST_GAP_MS));
      }
      burstRef.current = burst;
      setLiveTaken(true);
    } finally {
      setBusy(false);
    }
  }

  function submit() {
    if (!canSubmit || !blobRef.current) return;
    // **Deliberately does not start a session.** A length-based guess about
    // whether this is the first document silently drops cross-document trust
    // propagation the moment it guesses wrong — "New traveller" below is the
    // only thing allowed to reset the session.
    putCapture({
      blob: blobRef.current,
      docType,
      source,
      // The scanner writes the file itself, so its EXIF is clean by
      // construction and the metadata checks would only produce noise. A file
      // handed over on a stick is a different story.
      uploaded: source === "upload",
      live: liveRef.current ?? undefined,
      liveFrames: burstRef.current.length ? burstRef.current : undefined,
    });
    navigate("/screening");
  }

  return (
    <div className="mx-auto grid w-full max-w-7xl gap-6 px-6 py-8 lg:grid-cols-[minmax(0,1fr)_26rem]">
      {/* ---- LEFT: capture area ---- */}
      <div className="min-w-0 space-y-5">
        {/* Header */}
        <div>
          <h1 className="text-[length:var(--text-screen)] font-semibold tracking-[-0.02em]">
            Capture the document
          </h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-3">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-bloom border border-iris/40 px-3 py-1 text-label text-iris-ink">
              <span className="h-1.5 w-1.5 rounded-full bg-guilloche" />
              Session <span className="data font-medium">{sessionId}</span>
            </span>
            {documents.length > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-200 px-3 py-1 text-label text-emerald-700 font-medium">
                <CheckIcon size={11} /> {documents.length} screened
              </span>
            )}
            <button
              type="button"
              onClick={() => { startSession(); resetCapture(); }}
              className="text-label text-iris-ink underline underline-offset-2 hover:text-intaglio"
            >
              New traveller
            </button>
          </div>
        </div>

        {/* Document type */}
        <div>
          <h2 className="text-label font-medium uppercase tracking-wide text-iris-ink">
            Document presented
          </h2>
          <div className="mt-2 flex flex-wrap gap-2">
            {DOC_TYPES.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setDocType(t)}
                aria-pressed={docType === t}
                className={cn(
                  "rounded-full border px-3.5 py-1.5 text-label font-medium transition-all hover:-translate-y-0.5",
                  docType === t
                    ? "border-guilloche bg-guilloche text-white"
                    : "border-iris/50 bg-white text-iris-ink hover:border-iris-ink hover:text-intaglio hover:shadow-sm",
                )}
              >
                {docLabel(t)}
              </button>
            ))}
          </div>
        </div>

        {/* Source selector */}
        <div className="grid grid-cols-3 gap-3">
          {SOURCES.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => { setSource(s.key); resetCapture(); }}
              className={cn(
                "rounded-[var(--radius-md)] border p-4 text-left transition-all hover:-translate-y-0.5 hover:shadow-sm",
                source === s.key
                  ? "border-guilloche bg-guilloche/8 ring-2 ring-guilloche/20"
                  : "border-iris/50 bg-white hover:border-iris-ink",
              )}
            >
              <s.Icon size={18} className={cn(source === s.key ? "text-guilloche" : "text-iris-ink")} />
              <span className={cn("mt-2 block font-semibold", source === s.key ? "text-guilloche" : "text-intaglio")}>
                {s.label}
              </span>
              <span className={cn("block text-label mt-0.5", source === s.key ? "text-guilloche/70" : "text-iris-ink")}>
                {s.hint}
              </span>
            </button>
          ))}
        </div>

        {/* Stage / viewer */}
        <div className="rounded-[var(--radius-xl)] bg-intaglio overflow-hidden">
          <div className="relative mx-auto aspect-[3/2] max-h-[54vh]">
            {/* Corner guides + vignette — "document under glass," not a flat
                dark rectangle. Purely decorative, so it's excluded from the
                tab order and hidden from screen readers. */}
            <div aria-hidden className="pointer-events-none absolute inset-0 z-10">
              <div
                className="absolute inset-0"
                style={{ boxShadow: "inset 0 0 80px 10px rgba(0,0,0,0.35)" }}
              />
              {([
                ["top-4 left-4", "border-t-2 border-l-2"],
                ["top-4 right-4", "border-t-2 border-r-2"],
                ["bottom-4 left-4", "border-b-2 border-l-2"],
                ["bottom-4 right-4", "border-b-2 border-r-2"],
              ] as const).map(([pos, borders]) => (
                <span key={pos} className={cn("absolute h-6 w-6 border-white/30", pos, borders)} />
              ))}
            </div>

            {preview ? (
              <img src={preview} alt="Captured document" className="h-full w-full object-contain" />
            ) : source === "camera" ? (
              <video ref={videoRef} muted playsInline className="h-full w-full object-contain" />
            ) : (
              <label
                htmlFor="capture-file"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.preventDefault(); onFile(e.dataTransfer.files[0]); }}
                className="flex h-full w-full cursor-pointer flex-col items-center justify-center border-2 border-dashed border-white/15 hover:border-guilloche/50 transition-colors"
              >
                <span className="text-[length:var(--text-evidence)] text-white/70 font-medium text-center px-8">
                  {source === "scanner"
                    ? "Place the document on the glass and scan"
                    : "Drop an image here, or choose a file"}
                </span>
                <span className="mt-2 text-label text-white/40">
                  Nothing leaves this machine. There is no upload.
                </span>
              </label>
            )}
          </div>

          {cameraError && (
            <div className="m-4 rounded-[var(--radius-md)] border border-amber-400/40 bg-amber-900/20 px-4 py-3 text-amber-300 text-label">
              {cameraError}
            </div>
          )}

          {/* ---- Step two: the traveller's own photograph ---- */}
          {(askingForFace || liveTaken || faceSkipped) && (
            <div className="mx-4 mb-4 rounded-[var(--radius-md)] border border-guilloche/30 bg-bloom/50 p-5">
              <h2 className="text-label font-medium uppercase tracking-wide text-iris-ink">
                Step 2 — the traveller
              </h2>

              {liveTaken ? (
                <>
                  <p className="mt-2 text-intaglio">
                    Traveller photographed. Their face will be compared against
                    the photo printed on the document.
                  </p>
                  <button
                    type="button"
                    onClick={() => { liveRef.current = null; burstRef.current = []; setLiveTaken(false); }}
                    className="mt-3 rounded-[var(--radius-md)] border border-iris/50 px-4 py-2 text-iris-ink hover:bg-white transition-colors"
                  >
                    Retake
                  </button>
                </>
              ) : faceSkipped ? (
                <>
                  <p className="mt-2 text-intaglio">
                    Screening without a live face. The comparison and the liveness
                    check will report that they could not run — which is not the
                    same as passing.
                  </p>
                  <button
                    type="button"
                    onClick={() => setFaceSkipped(false)}
                    className="mt-3 rounded-[var(--radius-md)] border border-iris/50 px-4 py-2 text-iris-ink hover:bg-white transition-colors"
                  >
                    Photograph them after all
                  </button>
                </>
              ) : (
                <>
                  <p className="mt-2 text-intaglio">
                    The document is accepted. Now photograph the person presenting
                    it — look at the camera.
                  </p>
                  <div className="mt-4 rounded-[var(--radius-md)] bg-intaglio p-3">
                    <video
                      ref={faceVideoRef}
                      muted
                      playsInline
                      className="mx-auto max-h-[30vh] w-full object-contain"
                    />
                  </div>
                  <div className="mt-4 flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={grabLive}
                      disabled={busy}
                      className="flex items-center gap-2 rounded-[var(--radius-md)] bg-intaglio px-5 py-2.5 font-semibold text-white hover:bg-intaglio/90 transition-colors disabled:opacity-60"
                    >
                      {busy ? "Hold still…" : (<><ShutterIcon size={16} /> Photograph the traveller</>)}
                    </button>
                    <button
                      type="button"
                      onClick={() => setFaceSkipped(true)}
                      className="rounded-[var(--radius-md)] border border-iris/50 px-4 py-2.5 text-iris-ink hover:bg-white transition-colors"
                    >
                      No traveller present — screen the document only
                    </button>
                  </div>
                  <p className="mt-3 text-label text-iris-ink">
                    Five frames are taken over about a second and a half, so the
                    blink check has a sequence to read. It needs a face at least
                    320 pixels wide — if the verdict says to step closer, that is
                    the camera, not the traveller.
                  </p>
                </>
              )}
            </div>
          )}

          {/* Actions bar */}
          <div className="flex flex-wrap gap-3 px-5 py-4 border-t border-white/10">
            <input
              ref={fileRef}
              id="capture-file"
              type="file"
              accept="image/*"
              className="sr-only"
              onChange={(e) => onFile(e.target.files?.[0])}
            />
            {source === "camera" ? (
              <button
                type="button"
                onClick={grabFrame}
                disabled={busy}
                className="flex items-center gap-2 rounded-[var(--radius-md)] bg-white px-5 py-2.5 font-semibold text-intaglio hover:bg-bloom transition-colors disabled:opacity-60"
              >
                {busy ? "Hold still…" : (<><ShutterIcon size={16} /> Take the sharpest frame</>)}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="flex items-center gap-2 rounded-[var(--radius-md)] bg-white px-5 py-2.5 font-semibold text-intaglio hover:bg-bloom transition-colors"
              >
                <UploadIcon size={16} /> Choose a file
              </button>
            )}
            {preview && (
              <button
                type="button"
                onClick={resetCapture}
                className="flex items-center gap-2 rounded-[var(--radius-md)] border border-white/20 px-4 py-2.5 text-white/70 hover:bg-white/10 transition-colors"
              >
                <RetakeIcon size={14} /> Capture again
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ---- RIGHT: quality gate panel ---- */}
      <aside className="min-w-0">
        <div className="sticky top-6 rounded-[var(--radius-xl)] border border-iris/40 bg-white overflow-hidden" style={{ boxShadow: "var(--shadow-lg)" }}>
          {/* Panel header */}
          <div className="border-b border-iris/30 bg-bloom/60 px-6 py-4">
            <h2 className="font-semibold text-[length:var(--text-evidence)]">Quality check</h2>
            <p className="mt-0.5 text-label text-iris-ink">Before we screen it</p>
          </div>

          <div className="px-6 py-5">
            {gates.length === 0 ? (
              <div className="flex flex-col items-center py-8 text-center">

                <p className="font-medium text-intaglio">Awaiting capture</p>
                <p className="mt-1 text-label text-iris-ink max-w-[22ch]">
                  Capture the document and its quality is checked here first.
                </p>
              </div>
            ) : (
              <>
                {/* Progress summary */}
                <div className="mb-5 flex items-center gap-3">
                  <div className="flex-1 rounded-full bg-iris/20 h-2 overflow-hidden">
                    <div
                      className={cn("h-full rounded-full transition-all duration-500", documentReady ? "bg-emerald-500" : "bg-red-400")}
                      style={{ width: `${(passCount / gates.length) * 100}%` }}
                    />
                  </div>
                  <span className={cn("text-label font-bold", documentReady ? "text-emerald-600" : "text-red-600")}>
                    {passCount}/{gates.length}
                  </span>
                </div>

                <ul className="divide-y divide-iris/20">
                  {gates.map((g) => <GateRow key={g.key} gate={g} />)}
                </ul>

                <button
                  type="button"
                  onClick={submit}
                  disabled={!canSubmit}
                  className={cn(
                    "mt-6 w-full rounded-[var(--radius-md)] px-4 py-3.5 text-[length:var(--text-evidence)] font-semibold transition-all",
                    canSubmit
                      ? "bg-guilloche text-white hover:bg-guilloche/90 shadow-sm shadow-guilloche/30"
                      : "cursor-not-allowed bg-iris/20 text-iris-ink",
                  )}
                >
                  {canSubmit
                    ? `→ Screen this ${docLabel(docType).toLowerCase()}`
                    : askingForFace
                      ? "Photograph the traveller first"
                      : "Re-capture before screening"}
                </button>

                {!canSubmit && !askingForFace && (
                  <p className="mt-3 rounded-[var(--radius-sm)] bg-amber-50 border border-amber-200 px-3 py-2 text-label text-amber-700">
                    Sharpness and resolution are hard blocks. Exposure and glare are warnings — screen anyway if this is the best light you have.
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      </aside>
    </div>
  );
}
