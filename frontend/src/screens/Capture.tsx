/**
 * Capture.
 *
 * Three sources, because a border post may have any of them: a flatbed
 * scanner, a file handed over on a stick, or a webcam pointed at the counter.
 * The webcam path also supplies the live face for 1:1 verification.
 *
 * Quality is graded before submission. The point is to catch a soft capture
 * while the traveller is still standing there, rather than returning an AMBER
 * "re-capture required" after they have moved on.
 */
import { useCallback, useEffect, useRef, useState } from "react";
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
import { cn } from "../lib/utils";

/** Frames in the liveness burst, and the gap between them.
 *
 *  Five frames over ~1.4 s. A blink lasts 100-400 ms, so this is wide enough
 *  to contain one and short enough that the traveller is not asked to hold
 *  still. `modules/face/liveness.py` needs at least four to answer at all. */
const BURST_FRAMES = 5;
const BURST_GAP_MS = 280;

const SOURCES: { key: CaptureSource; label: string; hint: string }[] = [
  { key: "scanner", label: "Scanner", hint: "Flatbed at the counter" },
  { key: "upload", label: "File", hint: "An image or a scanned PDF page" },
  { key: "camera", label: "Camera", hint: "Also captures the live face" },
];

function GateRow({ gate }: { gate: QualityGate }) {
  return (
    <li className="flex gap-3 border-t border-iris/60 py-3">
      <span
        className={cn(
          "mt-1.5 h-2.5 w-2.5 shrink-0",
          gate.ok ? "bg-clear" : "bg-detain",
        )}
      />
      <span className="min-w-0">
        <span className="block font-medium">{gate.label}</span>
        <span className={cn("block text-label", gate.ok ? "text-iris-ink" : "text-detain")}>
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

  const putCapture = useCapture((c) => c.put);
  /** The bytes themselves, kept out of React state - a Blob does not belong in
   *  a render cycle and nothing re-renders when it changes. */
  const blobRef = useRef<Blob | null>(null);
  const liveRef = useRef<Blob | null>(null);
  const burstRef = useRef<Blob[]>([]);
  const [cameraError, setCameraError] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  //  The camera used for the *traveller*, which is a different camera from the
  //  one that may have taken the document. At a counter the document goes on
  //  the glass and the person is photographed by the camera on the post; those
  //  are two captures whatever hardware takes them.
  const faceVideoRef = useRef<HTMLVideoElement>(null);
  const faceStreamRef = useRef<MediaStream | null>(null);

  const gates = reading ? gradeCapture(reading, source) : [];
  const documentReady = gates.length > 0 && isSubmittable(gates);

  //  Step two opens itself as soon as the document is accepted. The officer is
  //  *asked* for the face rather than having to find a button for it - a check
  //  nobody was prompted to run is a check that does not happen, and
  //  `face.match.cosine` then reports `inconclusive` for the rest of time.
  const askingForFace = documentReady && !liveTaken && !faceSkipped;
  const canSubmit = documentReady && !busy && !askingForFace;

  /** Stop the camera whenever we leave it. A live webcam light at an
   *  unattended counter is its own kind of problem. */
  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => stopCamera, [stopCamera]);

  useEffect(() => {
    if (source !== "camera") {
      stopCamera();
      return;
    }
    let cancelled = false;
    setCameraError(null);
    navigator.mediaDevices
      ?.getUserMedia({ video: { width: 1280, height: 720 } })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          void videoRef.current.play();
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCameraError(
            "No camera available. Use a file or the scanner instead — screening works the same way.",
          );
        }
      });
    return () => {
      cancelled = true;
      stopCamera();
    };
  }, [source, stopCamera]);

  const stopFaceCamera = useCallback(() => {
    faceStreamRef.current?.getTracks().forEach((t) => t.stop());
    faceStreamRef.current = null;
  }, []);

  useEffect(() => stopFaceCamera, [stopFaceCamera]);

  /** Open the camera for step two, and close it the moment step two is over.
   *
   *  Separate stream from the document camera rather than shared: the two are
   *  never on at once (the document is captured before the traveller is asked
   *  for), and sharing one `srcObject` across two elements loses the stream
   *  when React moves the node. */
  useEffect(() => {
    if (!askingForFace) {
      stopFaceCamera();
      return;
    }
    let cancelled = false;
    navigator.mediaDevices
      ?.getUserMedia({ video: { width: 1280, height: 720 } })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        faceStreamRef.current = stream;
        if (faceVideoRef.current) {
          faceVideoRef.current.srcObject = stream;
          void faceVideoRef.current.play();
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCameraError(
            "No camera available for the live face. Screen the document without it — the face comparison will report that it could not run.",
          );
        }
      });
    return () => {
      cancelled = true;
      stopFaceCamera();
    };
  }, [askingForFace, stopFaceCamera]);

  function acceptImage(img: HTMLImageElement | HTMLVideoElement, w: number, h: number, url: string) {
    setReading(measure(img, w, h));
    setPreview(url);
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
  function frameBlob(quality = 0.92,
                     element?: HTMLVideoElement | null): Promise<Blob | null> {
    const v = element ?? videoRef.current;
    if (!v || !v.videoWidth) return Promise.resolve(null);
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext("2d")!.drawImage(v, 0, 0);
    return new Promise((resolve) =>
      canvas.toBlob((b) => resolve(b), "image/jpeg", quality),
    );
  }

  /** The document frame. Only the document. */
  async function grabFrame() {
    const v = videoRef.current;
    if (!v || !v.videoWidth || busy) return;
    setBusy(true);
    try {
      const doc = await frameBlob();
      if (!doc) return;
      blobRef.current = doc;
      acceptImage(v, v.videoWidth, v.videoHeight, URL.createObjectURL(doc));
    } finally {
      setBusy(false);
    }
  }

  /** The traveller. A **separate** photograph, and that is the whole point.
   *
   *  It is tempting to reuse the document frame: at a counter one camera sees
   *  a person holding their card, so the face and the document are in the same
   *  picture. It would also be a guaranteed false match. `modules/face` locates
   *  both the document portrait and the live face with `largest(detect(...))`
   *  over the whole image, so handing it one frame twice makes it compare a
   *  face to itself and return a cosine of 1.0 - evidence that is not
   *  independent of what it claims to prove, which is the same failure as D48.
   *
   *  So: point the camera at the card, then at the person. Two photographs,
   *  which is what 1:1 verification means.
   *
   *  The burst for the blink check rides on this action, not the document one,
   *  for the same reason - it has to be frames of a face, not of a card. */
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
        // Lower quality: these are read for whether the eyes are open, never
        // for a field value, and five full-quality frames is a slow upload on
        // a checkpoint's connection.
        const f = await frameBlob(0.7, v);
        if (f) burst.push(f);
        if (i < BURST_FRAMES - 1) {
          await new Promise((r) => setTimeout(r, BURST_GAP_MS));
        }
      }
      burstRef.current = burst;
      setLiveTaken(true);
    } finally {
      setBusy(false);
    }
  }

  function submit() {
    if (!canSubmit || !blobRef.current) return;
    // **Deliberately does not start a session.** It used to call
    // `startSession()` whenever the local document list looked empty, which is
    // the normal state on this screen - so every capture minted a fresh
    // `sessionId`, and the second document of a session was screened against
    // an empty set of priors. Cross-document trust propagation is the headline
    // of this system and it was silently switched off by a convenience call.
    //
    // A session ends when the officer says it does, not when a screen mounts.
    // "New traveller" below is that control.
    putCapture({
      blob: blobRef.current,
      docType,
      source,
      // The scanner writes the file itself, so its EXIF is clean by
      // construction and the metadata checks would only produce noise
      // (CLAUDE.md). A file handed over on a stick is a different story.
      uploaded: source === "upload",
      live: liveRef.current ?? undefined,
      liveFrames: burstRef.current.length ? burstRef.current : undefined,
    });
    navigate("/screening");
  }

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-10 px-8 py-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
      {/* ---------------------------------------------------------- source */}
      <div className="min-w-0">
        <h1 className="text-[length:var(--text-screen)] font-semibold">
          Capture the document
        </h1>
        <p className="mt-1 flex flex-wrap items-center gap-x-2 text-iris-ink">
          <span>
            Session <span className="data">{sessionId}</span>
          </span>
          {documents.length > 0 && (
            <>
              <span className="inline-block h-3 w-px bg-iris" />
              <span>
                {documents.length} already screened — the next document is
                checked against {documents.length === 1 ? "it" : "them"}
              </span>
            </>
          )}
          <span className="inline-block h-3 w-px bg-iris" />
          <button
            type="button"
            onClick={() => {
              startSession();
              setPreview(null);
              setReading(null);
              blobRef.current = null;
              liveRef.current = null;
              burstRef.current = [];
              setLiveTaken(false);
            }}
            className="underline underline-offset-2 hover:text-intaglio"
          >
            New traveller
          </button>
        </p>

        <div className="mt-6">
          <h2 className="text-label uppercase tracking-wide text-iris-ink">
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
                  "border px-3 py-1.5 transition-colors",
                  docType === t
                    ? "border-intaglio bg-intaglio text-paper"
                    : "border-iris hover:bg-bloom",
                )}
              >
                {docLabel(t)}
              </button>
            ))}
          </div>
          {/* The officer selects the type at the counter, so the backend
              reports `not_applicable` for automatic classification rather
              than a confidence it has not earned (CLAUDE.md). */}
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          {SOURCES.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => {
                setSource(s.key);
                setPreview(null);
                setReading(null);
                blobRef.current = null;
                liveRef.current = null;
                burstRef.current = [];
                setLiveTaken(false);
                setFaceSkipped(false);
              }}
              className={cn(
                "border px-4 py-2 text-left transition-colors",
                source === s.key
                  ? "border-intaglio bg-intaglio text-paper"
                  : "border-iris hover:bg-bloom",
              )}
            >
              <span className="block">{s.label}</span>
              <span
                className={cn(
                  "block text-label",
                  source === s.key ? "text-bloom/80" : "text-iris-ink",
                )}
              >
                {s.hint}
              </span>
            </button>
          ))}
        </div>

        {/* -------------------------------------------------------- stage */}
        <div className="mt-6 bg-intaglio p-5">
          <div className="relative mx-auto aspect-[3/2] max-h-[52vh]">
            {preview ? (
              <img
                src={preview}
                alt="Captured document"
                className="h-full w-full object-contain"
              />
            ) : source === "camera" ? (
              <video
                ref={videoRef}
                muted
                playsInline
                className="h-full w-full object-contain"
              />
            ) : (
              <label
                htmlFor="capture-file"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  onFile(e.dataTransfer.files[0]);
                }}
                className="flex h-full w-full cursor-pointer flex-col items-center justify-center border-2 border-dashed border-bloom/40 px-8 text-center text-bloom/80 hover:border-guilloche hover:text-paper"
              >
                <span className="text-[length:var(--text-evidence)]">
                  {source === "scanner"
                    ? "Place the document on the glass and scan"
                    : "Drop an image here, or choose a file"}
                </span>
                <span className="mt-2 text-label">
                  Nothing leaves this machine. There is no upload.
                </span>
              </label>
            )}
          </div>

          {/* ---------------------------------------------- step two: the face */}
        {(askingForFace || liveTaken || faceSkipped) && (
          <div className="mt-6 border border-iris bg-bloom/30 p-5">
            <h2 className="text-label uppercase tracking-wide text-iris-ink">
              Step 2 — the traveller
            </h2>

            {liveTaken ? (
              <>
                <p className="mt-2">
                  Traveller photographed. Their face will be compared against
                  the photo printed on the document.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    liveRef.current = null;
                    burstRef.current = [];
                    setLiveTaken(false);
                  }}
                  className="mt-3 border border-iris px-4 py-2 hover:bg-bloom"
                >
                  Retake
                </button>
              </>
            ) : faceSkipped ? (
              <>
                <p className="mt-2">
                  Screening without a live face. The comparison and the liveness
                  check will report that they could not run — which is not the
                  same as passing.
                </p>
                <button
                  type="button"
                  onClick={() => setFaceSkipped(false)}
                  className="mt-3 border border-iris px-4 py-2 hover:bg-bloom"
                >
                  Photograph them after all
                </button>
              </>
            ) : (
              <>
                <p className="mt-2">
                  The document is accepted. Now photograph the person presenting
                  it — look at the camera.
                </p>
                <div className="mt-4 bg-intaglio p-4">
                  <video
                    ref={faceVideoRef}
                    muted
                    playsInline
                    className="mx-auto max-h-[34vh] w-full object-contain"
                  />
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={grabLive}
                    disabled={busy}
                    className="bg-intaglio px-4 py-2 text-paper hover:bg-guilloche hover:text-intaglio disabled:opacity-60"
                  >
                    {busy ? "Hold still\u2026" : "Photograph the traveller"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setFaceSkipped(true)}
                    className="border border-iris px-4 py-2 hover:bg-bloom"
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

        {cameraError && (
            <p className="mt-4 border border-dashed border-guilloche px-3 py-2 text-guilloche">
              {cameraError}
            </p>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
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
                className="bg-paper px-4 py-2 text-intaglio hover:bg-guilloche disabled:opacity-60"
              >
                {busy ? "Hold still\u2026" : "Photograph the document"}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="bg-paper px-4 py-2 text-intaglio hover:bg-guilloche"
              >
                Choose a file
              </button>
            )}
            {preview && (
              <button
                type="button"
                onClick={() => {
                  setPreview(null);
                  setReading(null);
                  blobRef.current = null;
                  liveRef.current = null;
                  burstRef.current = [];
                  setLiveTaken(false);
                  setFaceSkipped(false);
                }}
                className="border border-bloom/50 px-4 py-2 text-paper hover:bg-bloom/20"
              >
                Capture again
              </button>
            )}
          </div>
        </div>
      </div>

      {/* --------------------------------------------------------- quality */}
      <aside className="min-w-0 bg-bloom/40 p-6">
        <h2 className="text-[length:var(--text-evidence)]">Before we screen it</h2>
        <div className="mt-1 border-t border-intaglio" />

        {gates.length === 0 ? (
          <p className="pt-4 text-iris-ink">
            Capture the document and its quality is checked here first. A soft
            capture cannot be recovered downstream — the machine-readable zone
            either resolves or it does not.
          </p>
        ) : (
          <>
            <ul className="mt-2">
              {gates.map((g) => (
                <GateRow key={g.key} gate={g} />
              ))}
            </ul>

            <button
              type="button"
              onClick={submit}
              disabled={!canSubmit}
              className={cn(
                "mt-6 w-full px-4 py-3 text-[length:var(--text-evidence)] transition-colors",
                canSubmit
                  ? "bg-intaglio text-paper hover:bg-intaglio/90"
                  : "cursor-not-allowed border border-iris text-iris-ink",
              )}
            >
              {canSubmit
                ? `Screen this ${docLabel(docType).toLowerCase()}`
                : askingForFace
                  ? "Photograph the traveller first"
                  : "Re-capture before screening"}
            </button>

            {!canSubmit && (
              <p className="mt-3 text-label text-iris-ink">
                Sharpness and resolution are hard blocks. Exposure and glare are
                warnings — screen anyway if this is the best light you have.
              </p>
            )}
          </>
        )}
      </aside>
    </div>
  );
}
