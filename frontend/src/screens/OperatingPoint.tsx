/**
 * The operating point.
 *
 * context/DEMO.md Scene 4: "At 5,000 passengers a day, a 2% false rejection
 * rate is 100 secondary inspections. The checkpoint commander sets this, not
 * us."
 *
 * So the screen leads with people per day, not rates. The curve is the
 * evidence behind that number, and the handle is the control.
 *
 * Chart decisions, per the dataviz procedure:
 *   form      two rates against one threshold axis — one y-scale, never two
 *   colour    two categorical hues, validated: CVD ΔE 14.2, normal 17.3, both
 *             above the floor on the cream surface
 *   marks     2px lines, recessive grid, direct labels on both series
 *   a11y      legend, direct labels, a table of the same numbers, keyboard
 *             control on the handle
 */
import { useMemo, useRef, useState } from "react";
import { useSettings } from "../store/settings";
import {
  curve,
  dailyConsequence,
  equalErrorRate,
  far,
  frr,
} from "../domain/operatingPoint";
import { cn } from "../lib/utils";

const FAR_INK = "#DC2626"; // impostor admitted — the serious one
const FRR_INK = "#7C3AED"; // genuine traveller stopped

const W = 720;
const H = 320;
const PAD = { l: 56, r: 24, t: 16, b: 44 };
const LO = 0;
const HI = 0.9;

/** Rates span four orders of magnitude, so a linear y-axis renders FAR as a
 *  flat line on the floor. Square-root keeps both readable without the
 *  false precision a log axis implies at the zero end. */
const yScale = (v: number) => Math.sqrt(Math.min(1, Math.max(0, v)));

const x = (t: number) => PAD.l + ((t - LO) / (HI - LO)) * (W - PAD.l - PAD.r);
const y = (v: number) => PAD.t + (1 - yScale(v)) * (H - PAD.t - PAD.b);

const pct = (v: number) =>
  v >= 0.01 ? `${(v * 100).toFixed(1)}%` : `${(v * 100).toFixed(2)}%`;

export function OperatingPoint() {
  const { faceThreshold, dailyVolume, coverageFloor, amberAt, redAt, set } =
    useSettings();
  const [hoverT, setHoverT] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [showTable, setShowTable] = useState(false);

  const pts = useMemo(() => curve(LO, HI), []);
  const eer = useMemo(() => equalErrorRate(), []);
  const now = dailyConsequence(faceThreshold, dailyVolume);

  const path = (key: "far" | "frr") =>
    pts.map((p, i) => `${i ? "L" : "M"} ${x(p.t).toFixed(1)} ${y(p[key]).toFixed(1)}`).join(" ");

  function tFromEvent(clientX: number): number {
    const rect = svgRef.current!.getBoundingClientRect();
    const px = ((clientX - rect.left) / rect.width) * W;
    const t = LO + ((px - PAD.l) / (W - PAD.l - PAD.r)) * (HI - LO);
    return Math.min(HI, Math.max(LO, Math.round(t * 200) / 200));
  }

  const readT = hoverT ?? faceThreshold;

  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-8">
      <h1 className="text-[length:var(--text-screen)] font-semibold tracking-[-0.02em]">
        Operating point
      </h1>
      <p className="mt-1 max-w-[42rem] text-iris-ink">
        Where the face threshold sits decides who gets stopped and who gets
        through. There is no setting that avoids both. This is a command
        decision, so it lives here rather than in a config file.
      </p>

      {/* The consequence, in people. This is what the number means. */}
      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        <div className="rounded-[var(--radius-lg)] border border-iris/40 bg-bloom/40 p-5" style={{ boxShadow: "var(--shadow-sm)" }}>
          <p className="data text-[length:var(--text-verdict)] leading-none text-intaglio">
            {faceThreshold.toFixed(2)}
          </p>
          <p className="mt-2 text-label text-iris-ink">cosine threshold</p>
        </div>
        <div className="rounded-[var(--radius-lg)] border p-5" style={{ borderColor: FRR_INK + "40", boxShadow: "var(--shadow-sm)" }}>
          <p className="data text-[length:var(--text-verdict)] leading-none" style={{ color: FRR_INK }}>
            {now.stopped}
          </p>
          <p className="mt-2 text-label text-iris-ink">
            genuine travellers sent to secondary inspection, per day
          </p>
        </div>
        <div className="rounded-[var(--radius-lg)] border p-5" style={{ borderColor: FAR_INK + "40", boxShadow: "var(--shadow-sm)" }}>
          <p className="data text-[length:var(--text-verdict)] leading-none" style={{ color: FAR_INK }}>
            {now.admitted}
          </p>
          <p className="mt-2 text-label text-iris-ink">
            impostors the face check would let through, per day
          </p>
        </div>
      </div>

      <p className="mt-4 text-label text-iris-ink">
        At <span className="data">{dailyVolume.toLocaleString("en-IN")}</span>{" "}
        crossings a day.
      </p>

      {/* --------------------------------------------------------- the curve */}
      <figure className="mt-10 rounded-[var(--radius-lg)] border border-iris/40 bg-bloom/30 p-6" style={{ boxShadow: "var(--shadow-sm)" }}>
        <figcaption className="flex flex-wrap items-center gap-6">
          <span className="text-[length:var(--text-evidence)] font-semibold">
            How the two errors trade off
          </span>
          <span className="ml-auto flex gap-5 text-label">
            <span className="inline-flex items-center gap-2">
              <span className="h-0.5 w-5 rounded-full" style={{ background: FRR_INK }} />
              <span className="text-intaglio">Genuine stopped (FRR)</span>
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="h-0.5 w-5 rounded-full" style={{ background: FAR_INK }} />
              <span className="text-intaglio">Impostor admitted (FAR)</span>
            </span>
          </span>
        </figcaption>

        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="mt-3 w-full cursor-ew-resize touch-none select-none"
          role="img"
          aria-label={`False rejection and false acceptance against the cosine threshold. At ${faceThreshold.toFixed(2)}, ${pct(frr(faceThreshold))} of genuine travellers are stopped and ${pct(far(faceThreshold))} of impostors are admitted.`}
          onMouseMove={(e) => setHoverT(tFromEvent(e.clientX))}
          onMouseLeave={() => setHoverT(null)}
          onClick={(e) => set({ faceThreshold: tFromEvent(e.clientX) })}
        >
          {/* recessive grid */}
          {[0.001, 0.01, 0.05, 0.2, 0.5, 1].map((v) => (
            <g key={v}>
              <line
                x1={PAD.l}
                x2={W - PAD.r}
                y1={y(v)}
                y2={y(v)}
                stroke="var(--color-iris)"
                strokeWidth="0.5"
                opacity="0.5"
              />
              <text
                x={PAD.l - 8}
                y={y(v) + 4}
                textAnchor="end"
                fontSize="11"
                fill="var(--color-iris-ink)"
                fontFamily="DM Mono, monospace"
              >
                {pct(v)}
              </text>
            </g>
          ))}
          {[0, 0.2, 0.4, 0.6, 0.8].map((t) => (
            <text
              key={t}
              x={x(t)}
              y={H - PAD.b + 20}
              textAnchor="middle"
              fontSize="11"
              fill="var(--color-iris-ink)"
              fontFamily="DM Mono, monospace"
            >
              {t.toFixed(1)}
            </text>
          ))}
          <text
            x={(PAD.l + W - PAD.r) / 2}
            y={H - 6}
            textAnchor="middle"
            fontSize="12"
            fill="var(--color-iris-ink)"
          >
            cosine threshold
          </text>

          {/* equal error rate, as a landmark rather than a recommendation */}
          <line
            x1={x(eer.t)}
            x2={x(eer.t)}
            y1={PAD.t}
            y2={H - PAD.b}
            stroke="var(--color-iris)"
            strokeWidth="1"
            strokeDasharray="4 4"
          />
          <text
            x={x(eer.t) - 6}
            y={PAD.t + 12}
            textAnchor="end"
            fontSize="11"
            fill="var(--color-iris-ink)"
          >
            equal error
          </text>

          {/* 2px marks, no fills */}
          <path d={path("frr")} fill="none" stroke={FRR_INK} strokeWidth="2" />
          <path d={path("far")} fill="none" stroke={FAR_INK} strokeWidth="2" />

          {/* direct labels — identity is never colour alone */}
          <text x={x(0.78)} y={y(frr(0.78)) - 10} fontSize="12" fill={FRR_INK} fontWeight="600">
            genuine stopped
          </text>
          <text x={x(0.06)} y={y(far(0.06)) - 10} fontSize="12" fill={FAR_INK} fontWeight="600">
            impostor admitted
          </text>

          {/* the handle */}
          <line
            x1={x(readT)}
            x2={x(readT)}
            y1={PAD.t}
            y2={H - PAD.b}
            stroke="var(--color-intaglio)"
            strokeWidth="1.5"
          />
          <circle cx={x(readT)} cy={y(frr(readT))} r="6" fill={FRR_INK} stroke="var(--color-paper)" strokeWidth="2" />
          <circle cx={x(readT)} cy={y(far(readT))} r="6" fill={FAR_INK} stroke="var(--color-paper)" strokeWidth="2" />
        </svg>

        {/* readout follows the pointer, settles on the set value */}
        <p className="mt-2 text-label text-iris-ink">
          At threshold <span className="data text-intaglio">{readT.toFixed(2)}</span>
          <span className="mx-2 inline-block h-3 w-px translate-y-0.5 bg-iris" />
          <span className="data" style={{ color: FRR_INK }}>{pct(frr(readT))}</span> of
          genuine travellers stopped
          <span className="mx-2 inline-block h-3 w-px translate-y-0.5 bg-iris" />
          <span className="data" style={{ color: FAR_INK }}>{pct(far(readT))}</span> of
          impostors admitted
          {hoverT !== null && " — click to set"}
        </p>
      </figure>

      {/* keyboard control, because a chart you can only drag is not usable */}
      <label className="mt-8 block">
        <span className="text-label font-medium text-iris-ink">Threshold</span>
        <input
          type="range"
          min={0}
          max={0.9}
          step={0.005}
          value={faceThreshold}
          onChange={(e) => set({ faceThreshold: Number(e.target.value) })}
          className="mt-2 w-full accent-guilloche"
        />
      </label>

      <button
        type="button"
        onClick={() => setShowTable((v) => !v)}
        className="mt-4 text-label text-guilloche font-medium underline-offset-4 hover:underline"
      >
        {showTable ? "Hide" : "Show"} the same numbers as a table
      </button>

      {showTable && (
        <div className="mt-4 rounded-[var(--radius-md)] border border-iris/40 overflow-hidden">
          <table className="w-full max-w-xl">
            <thead>
              <tr className="border-b border-iris/40 bg-bloom/50 text-left text-label text-iris-ink">
                <th className="py-2.5 pl-4 font-medium">Threshold</th>
                <th className="py-2.5 font-medium">Genuine stopped</th>
                <th className="py-2.5 font-medium">Impostors admitted</th>
                <th className="py-2.5 pr-4 font-medium">Per day</th>
              </tr>
            </thead>
            <tbody>
              {[0.1, 0.2, 0.25, 0.32, 0.4, 0.5, 0.6].map((t) => {
                const c = dailyConsequence(t, dailyVolume);
                return (
                  <tr
                    key={t}
                    className={cn(
                      "border-b border-iris/30 data",
                      Math.abs(t - faceThreshold) < 0.005 && "bg-guilloche/10",
                    )}
                  >
                    <td className="py-2.5 pl-4">{t.toFixed(2)}</td>
                    <td className="py-2.5">{pct(frr(t))}</td>
                    <td className="py-2.5">{pct(far(t))}</td>
                    <td className="py-2.5 pr-4">
                      {c.stopped} stopped, {c.admitted} admitted
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ------------------------------------------------ the other dials */}
      <section className="mt-14">
        <h2 className="text-[length:var(--text-evidence)] font-semibold">Verdict bands</h2>
        <div className="mt-2 h-px bg-iris/60" />
        <p className="mt-4 max-w-[42rem] text-iris-ink">
          Changing any of these re-scores every historical event from its stored
          signals. Nothing is re-inferred, so the audit trail stays comparable.
        </p>

        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          {[
            { key: "amberAt" as const, label: "Secondary above", value: amberAt },
            { key: "redAt" as const, label: "Detain above", value: redAt },
            { key: "coverageFloor" as const, label: "Coverage floor", value: coverageFloor },
          ].map((f) => (
            <label key={f.key} className="block">
              <span className="text-label font-medium text-iris-ink">{f.label}</span>
              <input
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={f.value}
                onChange={(e) => set({ [f.key]: Number(e.target.value) })}
                className="mt-2 w-full rounded-[var(--radius-md)] border border-iris/60 bg-paper px-3 py-2.5 data focus:border-guilloche focus:ring-1 focus:ring-guilloche/30 transition-colors"
              />
            </label>
          ))}
        </div>

        <label className="mt-6 block max-w-xs">
          <span className="text-label font-medium text-iris-ink">Crossings per day</span>
          <input
            type="number"
            min={100}
            step={100}
            value={dailyVolume}
            onChange={(e) => set({ dailyVolume: Number(e.target.value) })}
            className="mt-2 w-full rounded-[var(--radius-md)] border border-iris/60 bg-paper px-3 py-2.5 data focus:border-guilloche focus:ring-1 focus:ring-guilloche/30 transition-colors"
          />
        </label>
      </section>
    </div>
  );
}
