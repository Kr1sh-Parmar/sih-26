/**
 * Document face against live face.
 *
 * The gauge shows the cosine and its signed distance from the operating
 * threshold, and nothing else. There is no 0-100 number here by design:
 * `((cos + 1) / 2) * 100` maps a stranger to 50, which misleads in the
 * direction that admits fraudsters.
 *
 * The officer needs to know how close the call was. That is the margin.
 */
import type { ReactNode } from "react";
import type { Region } from "../contracts";
import { faceMargin, FACE_BAND_LABEL, gaugePosition } from "../domain/faceMargin";
import { cn } from "../lib/utils";

interface Props {
  cosine: number | null;
  threshold: number;
  /** Null until the live camera has a frame. */
  liveReady?: boolean;
  /** The full document image, when a real capture is on screen — null for a
   *  replayed fixture, which has no image to crop from. */
  docImageSrc?: string | null;
  /** The document face's box, in the document's own canvas coordinates.
   *  Comes straight off `face.match.cosine` / `face.doc.quality`'s `region` —
   *  the same field DocumentViewer already draws its overlay boxes from. */
  docRegion?: Region | null;
  docCanvas?: readonly [number, number] | null;
  /** The traveller's own photograph. Kept client-side only — the backend
   *  never stores or returns the live crop, so this is the browser's own
   *  capture, still in memory from before it was uploaded. */
  liveImageSrc?: string | null;
}

function FaceWell({ label, empty, children }: { label: string; empty?: boolean; children?: ReactNode }) {
  return (
    <div className="flex-1">
      <div className="relative aspect-[3/4] rounded-[var(--radius-md)] bg-intaglio/90 overflow-hidden">
        {empty ? (
          <div className="absolute inset-0 grid place-items-center px-4 text-center text-label text-white/50">
            Waiting for the camera
          </div>
        ) : children ? (
          children
        ) : (
          <svg viewBox="0 0 60 80" className="h-full w-full" aria-hidden>
            <circle cx="30" cy="28" r="14" fill="var(--color-iris)" opacity="0.7" />
            <path d="M 8 80 q 22 -30 44 0 Z" fill="var(--color-iris)" opacity="0.7" />
          </svg>
        )}
      </div>
      <p className="mt-2 text-label text-iris-ink">{label}</p>
    </div>
  );
}

export function FacePair({
  cosine,
  threshold,
  liveReady = true,
  docImageSrc,
  docRegion,
  docCanvas,
  liveImageSrc,
}: Props) {
  const r = faceMargin(cosine, threshold);
  const noFace = r.band === "no_face";

  const bandInk =
    r.band === "match"
      ? "text-clear"
      : r.band === "no_match"
        ? "text-detain"
        : "text-secondary-ink";

  // Crop the document's own face box out of the full page image with an SVG
  // viewBox — `preserveAspectRatio="xMidYMid slice"` is `object-fit: cover`
  // for a sub-rectangle, so the well fills edge-to-edge regardless of the
  // detector's box aspect ratio, with no canvas element needed.
  const docCrop = docImageSrc && docRegion && docCanvas && (
    <svg
      viewBox={`${docRegion[0]} ${docRegion[1]} ${docRegion[2] - docRegion[0]} ${docRegion[3] - docRegion[1]}`}
      preserveAspectRatio="xMidYMid slice"
      className="h-full w-full"
    >
      <image href={docImageSrc} width={docCanvas[0]} height={docCanvas[1]} />
    </svg>
  );

  const liveCrop = liveImageSrc && (
    <img src={liveImageSrc} alt="The traveller as photographed at the counter" className="h-full w-full object-cover" />
  );

  return (
    <section className="mt-8">
      <div className="flex gap-4">
        <FaceWell label="From the document">{docCrop}</FaceWell>
        <FaceWell label="From the camera" empty={!liveReady}>{liveCrop}</FaceWell>
      </div>

      <p className={cn("mt-4 text-[length:var(--text-evidence)] font-medium", noFace ? "text-iris-ink" : bandInk)}>
        {FACE_BAND_LABEL[r.band]}
      </p>

      {noFace ? (
        <p className="mt-1 text-label text-iris-ink">
          No usable face in the document photo. Ask for a higher-resolution
          capture of the document — the printed photo cannot be retaken.
        </p>
      ) : (
        <>
          <p className="mt-1 text-label text-iris-ink">
            cosine <span className="data">{r.cosine!.toFixed(2)}</span>
            <span className="mx-2 inline-block h-3 w-px translate-y-0.5 bg-iris" />
            <span className="data">
              {r.margin! >= 0 ? "+" : ""}
              {r.margin!.toFixed(2)}
            </span>{" "}
            from the {threshold.toFixed(2)} threshold
          </p>

          {/* The scale is the cosine range, with the threshold marked. */}
          <div className="relative mt-3 h-8">
            <div className="absolute top-3.5 h-px w-full rounded-full bg-iris" />
            <div
              className="absolute top-1 h-6 w-px bg-intaglio"
              style={{ left: `${gaugePosition(threshold) * 100}%` }}
            />
            <div
              className={cn(
                "absolute top-2 h-4 w-4 -translate-x-1/2 rounded-full border-2 border-paper",
                r.band === "match" ? "bg-clear" : r.band === "no_match" ? "bg-detain" : "bg-secondary-ink",
              )}
              style={{ left: `${gaugePosition(r.cosine!) * 100}%` }}
            />
          </div>
          <div className="flex justify-between text-label text-iris-ink">
            <span>no match</span>
            <span>threshold</span>
            <span>match</span>
          </div>
        </>
      )}
    </section>
  );
}
