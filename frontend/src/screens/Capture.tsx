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
import { cn } from "../lib/utils";

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
  const [preview, setPreview] = useState<string | null>(null);
  const [reading, setReading] = useState<QualityReading | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const gates = reading ? gradeCapture(reading, source) : [];
  const canSubmit = gates.length > 0 && isSubmittable(gates);

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

  function acceptImage(img: HTMLImageElement | HTMLVideoElement, w: number, h: number, url: string) {
    setReading(measure(img, w, h));
    setPreview(url);
  }

  function onFile(file: File | undefined) {
    if (!file) return;
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => acceptImage(img, img.naturalWidth, img.naturalHeight, url);
    img.onerror = () => URL.revokeObjectURL(url);
    img.src = url;
  }

  function grabFrame() {
    const v = videoRef.current;
    if (!v || !v.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext("2d")!.drawImage(v, 0, 0);
    acceptImage(v, v.videoWidth, v.videoHeight, canvas.toDataURL("image/jpeg", 0.92));
  }

  function submit() {
    if (!canSubmit) return;
    if (documents.length === 0) startSession();
    navigate("/screening");
  }

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-10 px-8 py-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
      {/* ---------------------------------------------------------- source */}
      <div className="min-w-0">
        <h1 className="text-[length:var(--text-screen)] font-semibold">
          Capture the document
        </h1>
        <p className="mt-1 text-iris-ink">
          Session <span className="data">{sessionId}</span>
          {documents.length > 0 && (
            <>
              <span className="mx-2 inline-block h-3 w-px translate-y-0.5 bg-iris" />
              {documents.length} already screened in this session
            </>
          )}
        </p>

        <div className="mt-6 flex flex-wrap gap-2">
          {SOURCES.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => {
                setSource(s.key);
                setPreview(null);
                setReading(null);
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
                className="bg-paper px-4 py-2 text-intaglio hover:bg-guilloche"
              >
                Take the sharpest frame
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
              {canSubmit ? "Screen this document" : "Re-capture before screening"}
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
