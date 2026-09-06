/**
 * Drawn specimens, standing in for the generator's output.
 *
 * CLAUDE.md hard rule #4: no real government document goes anywhere near this
 * repository. Until data/generator/ produces templates, the viewer draws a
 * schematic instead — obviously synthetic, correct in layout, and in the same
 * coordinate space as the fixture regions so the overlay is exercised for real.
 *
 * Replace the whole file with an <image> when the generator lands. The
 * coordinate space (meta.canvas) is the contract between the two.
 */

const GUILLOCHE_ID = "guilloche-lathe";

/** Lathe-work underprint. Two interfering sine families, which is roughly how
 *  the real thing is made. */
function Guilloche() {
  const lines = Array.from({ length: 26 }, (_, i) => {
    const phase = (i / 26) * Math.PI * 2;
    const pts: string[] = [];
    for (let x = 0; x <= 100; x += 2) {
      const t = (x / 100) * Math.PI * 4;
      const y = 50 + Math.sin(t + phase) * 22 + Math.sin(t * 2.7 + phase) * 12;
      pts.push(`${x},${y.toFixed(2)}`);
    }
    return pts.join(" ");
  });
  return (
    <pattern id={GUILLOCHE_ID} width="100" height="100" patternUnits="userSpaceOnUse">
      {lines.map((pts, i) => (
        <polyline
          key={i}
          points={pts}
          fill="none"
          stroke="var(--color-iris)"
          strokeWidth="0.22"
          opacity="0.5"
        />
      ))}
    </pattern>
  );
}

/** A generic head-and-shoulders silhouette. Not a person. */
function Portrait({ x, y, w, h, ghost = false }: { x: number; y: number; w: number; h: number; ghost?: boolean }) {
  const cx = x + w / 2;
  return (
    <g opacity={ghost ? 0.28 : 1}>
      <rect x={x} y={y} width={w} height={h} fill="var(--color-bloom)" />
      <circle cx={cx} cy={y + h * 0.34} r={w * 0.24} fill="var(--color-iris)" />
      <path
        d={`M ${cx - w * 0.36} ${y + h} q ${w * 0.36} ${-h * 0.42} ${w * 0.72} 0 Z`}
        fill="var(--color-iris)"
      />
      <rect x={x} y={y} width={w} height={h} fill="none" stroke="var(--color-intaglio)" strokeWidth="2" />
    </g>
  );
}

function Line({ x, y, w, label, value, mono }: {
  x: number; y: number; w: number; label: string; value: string; mono?: boolean;
}) {
  return (
    <g>
      <text x={x} y={y} fill="var(--color-iris-ink)" fontSize="17" letterSpacing="0.4">
        {label}
      </text>
      <text
        x={x}
        y={y + 34}
        fill="var(--color-intaglio)"
        fontSize="30"
        fontFamily={mono ? "DM Mono, monospace" : "Archivo, sans-serif"}
        fontWeight="500"
      >
        {value}
      </text>
      <line x1={x} y1={y + 44} x2={x + w} y2={y + 44} stroke="var(--color-iris)" strokeWidth="0.8" />
    </g>
  );
}

export function PassportSpecimen({ fields }: { fields: Record<string, string> }) {
  return (
    <svg viewBox="0 0 1654 1170" className="h-full w-full" role="img"
         aria-label="Synthetic passport data page, drawn specimen">
      <defs><Guilloche /></defs>
      <rect width="1654" height="1170" fill="var(--color-paper)" />
      <rect width="1654" height="1170" fill={`url(#${GUILLOCHE_ID})`} />

      <text x="90" y="120" fill="var(--color-intaglio)" fontSize="44" fontWeight="700"
            letterSpacing="6">REPUBLIC OF INDIA</text>
      <text x="90" y="164" fill="var(--color-iris-ink)" fontSize="22" letterSpacing="4">
        SPECIMEN — GENERATED, NOT A REAL DOCUMENT
      </text>
      <line x1="90" y1="196" x2="1564" y2="196" stroke="var(--color-intaglio)" strokeWidth="2" />

      <Portrait x={110} y={300} w={370} h={500} />
      <Portrait x={1300} y={560} w={180} h={240} ghost />

      <Line x={600} y={250} w={400} label="Passport No." value={fields.id_number ?? ""} mono />
      <Line x={600} y={360} w={650} label="Surname and given names" value={fields.name ?? ""} />
      <Line x={1020} y={360} w={310} label="Nationality" value={fields.nationality ?? "IND"} />
      <Line x={600} y={470} w={350} label="Date of birth" value={fields.dob ?? ""} mono />
      <Line x={600} y={580} w={350} label="Date of expiry" value={fields.expiry_date ?? ""} mono />

      {/* MRZ — two lines of 44, OCR-B, on a clean band */}
      <rect x="90" y="900" width="1474" height="150" fill="var(--color-paper)" />
      <text x="104" y="960" fontFamily="DM Mono, monospace" fontSize="37"
            fill="var(--color-intaglio)" letterSpacing="2.4">
        {`P<IND${(fields.name ?? "").replace(/ /g, "<<")}`.padEnd(44, "<").slice(0, 44)}
      </text>
      <text x="104" y="1020" fontFamily="DM Mono, monospace" fontSize="37"
            fill="var(--color-intaglio)" letterSpacing="2.4">
        {`${(fields.id_number ?? "").padEnd(9, "<")}3IND${(fields.dob ?? "").replace(/-/g, "").slice(2)}7M${(fields.expiry_date ?? "").replace(/-/g, "").slice(2)}4`
          .padEnd(44, "<").slice(0, 44)}
      </text>
    </svg>
  );
}

export function PanSpecimen({ fields }: { fields: Record<string, string> }) {
  return (
    <svg viewBox="0 0 1400 900" className="h-full w-full" role="img"
         aria-label="Synthetic PAN card, drawn specimen">
      <defs><Guilloche /></defs>
      <rect width="1400" height="900" fill="var(--color-paper)" />
      <rect width="1400" height="900" fill={`url(#${GUILLOCHE_ID})`} />

      <text x="110" y="110" fill="var(--color-intaglio)" fontSize="38" fontWeight="700"
            letterSpacing="3">INCOME TAX DEPARTMENT</text>
      <text x="110" y="156" fill="var(--color-iris-ink)" fontSize="20" letterSpacing="3">
        SPECIMEN — GENERATED, NOT A REAL DOCUMENT
      </text>
      <line x1="110" y1="192" x2="1290" y2="192" stroke="var(--color-intaglio)" strokeWidth="2" />

      <Portrait x={1080} y={300} w={250} h={320} />

      <Line x={110} y={300} w={690} label="Name" value={fields.name ?? ""} />
      <Line x={110} y={390} w={690} label="Father's name" value={fields.father_name ?? ""} />
      <Line x={110} y={480} w={450} label="Date of birth" value={fields.dob ?? ""} mono />
      <Line x={110} y={640} w={510} label="Permanent Account Number" value={fields.id_number ?? ""} mono />
    </svg>
  );
}

export function Specimen({ docType, fields }: { docType: string; fields: Record<string, string> }) {
  if (docType === "pan") return <PanSpecimen fields={fields} />;
  return <PassportSpecimen fields={fields} />;
}
