/**
 * The document under glass, with the region overlay.
 *
 * The link between an evidence card and the place on the document it refers to
 * is what makes the evidence checkable by a human rather than asserted by a
 * model. It runs in both directions through `activeAnchor`.
 *
 * Regions arrive in the warped image's own coordinate space (meta.canvas).
 * Everything here works in that space and lets the SVG viewBox do the mapping,
 * so nothing silently breaks when the panel is resized — the failure mode of
 * hand-rolled pixel maths.
 */
import { useMemo } from "react";
import { motion, useReducedMotion } from "motion/react";
import type { Region, Signal } from "../contracts";
import { useScreening } from "../store/screening";
import { Specimen } from "./Specimen";
import { cn } from "../lib/utils";

interface Props {
  docType: string;
  canvas: [number, number];
  fields: { name: string; value: string; region: Region | null }[];
  /** The capture itself, when there is one to show.
   *
   *  A replayed fixture has no image and falls back to the drawn specimen; a
   *  document the officer actually put on the glass has one, and showing them
   *  a passport drawing while they screen an Aadhaar is the kind of detail
   *  that makes a working system look broken. */
  imageSrc?: string | null;
  signals: Signal[];
}

/** One box per anchor, taking the first region any signal on that anchor
 *  carries. Four signals on one altered date of birth is one box, not four. */
function regionsByAnchor(signals: Signal[], fields: Props["fields"]) {
  const map = new Map<string, { region: Region; failing: boolean }>();
  for (const f of fields) {
    if (f.region) map.set(`field:${f.name}`, { region: f.region, failing: false });
  }
  for (const s of signals) {
    if (!s.region) continue;
    const existing = map.get(s.anchor);
    const failing = s.verdict === "fail";
    if (!existing) map.set(s.anchor, { region: s.region, failing });
    else if (failing) existing.failing = true;
  }
  return map;
}

export function DocumentViewer({ docType, canvas, fields, signals, imageSrc }: Props) {
  const activeAnchor = useScreening((s) => s.activeAnchor);
  const setActiveAnchor = useScreening((s) => s.setActiveAnchor);
  const reduce = useReducedMotion();

  const [w, h] = canvas;
  const boxes = useMemo(() => regionsByAnchor(signals, fields), [signals, fields]);
  const values = useMemo(
    () => Object.fromEntries(fields.map((f) => [f.name, f.value])),
    [fields],
  );

  return (
    <div className="relative bg-intaglio p-5">
      <div className="relative mx-auto max-h-[46vh]" style={{ aspectRatio: `${w} / ${h}`, maxWidth: `calc(46vh * ${w} / ${h})` }}>
        {imageSrc ? (
          <img
            src={imageSrc}
            alt="The document as captured"
            className="absolute inset-0 h-full w-full object-contain"
          />
        ) : (
          <Specimen docType={docType} fields={values} />
        )}

        <svg
          viewBox={`0 0 ${w} ${h}`}
          className="absolute inset-0 h-full w-full"
          aria-hidden={boxes.size === 0}
        >
          {[...boxes.entries()].map(([anchor, { region, failing }]) => {
            const [x1, y1, x2, y2] = region;
            const active = activeAnchor === anchor;
            return (
              <motion.rect
                key={anchor}
                x={x1}
                y={y1}
                width={x2 - x1}
                height={y2 - y1}
                fill={active ? "var(--color-guilloche)" : "transparent"}
                fillOpacity={active ? 0.22 : 0}
                stroke={
                  failing
                    ? "var(--color-detain-lit)"
                    : active
                      ? "var(--color-guilloche)"
                      : "var(--color-iris-ink)"
                }
                strokeWidth={active ? 6 : failing ? 5 : 2.5}
                strokeDasharray={failing || active ? undefined : "10 8"}
                className="cursor-pointer"
                onMouseEnter={() => setActiveAnchor(anchor)}
                onMouseLeave={() => setActiveAnchor(null)}
                initial={reduce ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.2 }}
              />
            );
          })}
        </svg>
      </div>

      <p className={cn("mt-4 text-label", "text-bloom/70")}>
        {imageSrc
          ? "The capture as screened. Every document here is generated \u2014 no real identity document appears anywhere in this repository."
          : "Drawn specimen. This is a replayed case, not a capture \u2014 no real document appears anywhere in this repository."}
      </p>
    </div>
  );
}
