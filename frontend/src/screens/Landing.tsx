/**
 * Landing page.
 *
 * The panel reading this is the Ministry of Home Affairs, not a buyer. So the
 * page opens with the idea the system is built on — three levels of certainty,
 * and telling the officer which one a verdict came from — rather than a
 * headline and a call to action.
 *
 * The honest-limits section is deliberate. context/DEMO.md Scene 5: knowing
 * your limits "buys more credibility than any number."
 */
import { Link } from "react-router-dom";
import type { TrustClass } from "../contracts";
import { TrustMark } from "../components/marks/TrustMark";

const LADDER: { trust: TrustClass; name: string; example: string; certainty: string }[] = [
  {
    trust: "cryptographic",
    name: "Cryptographic",
    example: "An Ed25519 signature verifies against a key we already trust.",
    certainty: "Certain",
  },
  {
    trust: "arithmetic",
    name: "Arithmetic",
    example:
      "Five MRZ check digits, Verhoeff on a twelve-digit Aadhaar, a date that cannot precede its own issue.",
    certainty: "Deterministic. No model, no key.",
  },
  {
    trust: "probabilistic",
    name: "Probabilistic",
    example:
      "A tamper heuristic, a face embedding, an OCR confidence. Useful, and fallible.",
    certainty: "Can be wrong",
  },
  {
    trust: "unverified",
    name: "Unverified",
    example:
      "The fallback reader produced a value with no checksum behind it.",
    certainty: "Never enough for a clear verdict on its own",
  },
];

const PIPELINE = [
  { stage: "Decode and quality gate", ms: 60 },
  { stage: "Segment and correct perspective", ms: 45 },
  { stage: "Classify the document type", ms: 15 },
  { stage: "Detect the 22 field classes", ms: 110 },
  { stage: "Read about ten field crops", ms: 280 },
  { stage: "Parse the MRZ, run every validation layer", ms: 25 },
  { stage: "Match the face, check liveness", ms: 320 },
  { stage: "Cheap tamper forensics", ms: 160 },
  { stage: "Weigh the evidence", ms: 5 },
];

const LIMITS = [
  "Every document in our dataset is generated. Real forged passports are not obtainable, for obvious reasons, so our tamper accuracy is measured against forgeries we made ourselves and labelled as such.",
  "The signatures are ours. Four of six Indian identity documents carry no cryptographic integrity today, so we built a reference issuer and say so in the interface. Swapping in a real government key changes no code.",
  "A professional forgery with matched materials would likely pass our physical checks. The system assists an officer; it does not decide.",
  "Face recognition carries measurable demographic disparity. The officer sees the margin from the threshold, and the officer decides.",
];

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mx-auto w-full max-w-5xl px-8 py-16">
      <h2 className="text-[length:var(--text-screen)] font-semibold tracking-[-0.02em]">{title}</h2>
      <div className="mt-3 h-px bg-iris/60" />
      {children}
    </section>
  );
}

export function Landing() {
  const total = PIPELINE.reduce((a, s) => a + s.ms, 0);
  const widest = Math.max(...PIPELINE.map((s) => s.ms));

  return (
    <div className="min-h-screen bg-paper">
      {/* ------------------------------------------------------------ hero */}
      <header className="bg-intaglio px-8 py-4 text-paper">
        <div className="mx-auto flex max-w-5xl items-center gap-6">
          <span className="text-[length:var(--text-evidence)] font-semibold tracking-[-0.02em]">Sashastra Seema Bal</span>
          <span className="hidden sm:inline-block h-4 w-px bg-white/20" />
          <span className="hidden sm:inline text-white/60">Identity document screening</span>
          <Link
            to="/capture"
            className="ml-auto rounded-[var(--radius-md)] bg-guilloche px-5 py-2 text-label font-medium text-white hover:bg-guilloche/90 transition-colors"
          >
            Open the console
          </Link>
        </div>
      </header>

      <div className="mx-auto w-full max-w-5xl px-8 pt-20 pb-4">
        <p className="text-label font-medium text-guilloche tracking-wide uppercase">
          Smart India Hackathon 26188 — Ministry of Home Affairs
        </p>
        <h1 className="mt-4 max-w-3xl text-[length:var(--text-verdict)] leading-[0.95] font-bold tracking-[-0.03em]">
          Three levels of certainty, and the officer is told which one.
        </h1>
        <p className="mt-8 max-w-[38rem] text-[length:var(--text-evidence)] leading-relaxed text-iris-ink">
          A document screening system for land border checkpoints. It reads an
          identity document, checks it at three levels of certainty, looks for
          tampering, matches the holder's face, and hands the officer a verdict
          with reasons they can check by eye. It runs on a commodity eight-core
          CPU with the network cable unplugged.
        </p>
      </div>

      {/* The ladder is the product. It goes first, before anything else. */}
      <div className="mx-auto w-full max-w-5xl px-8 pb-20">
        <ol className="mt-10 grid gap-4">
          {LADDER.map((row) => (
            <li
              key={row.trust}
              className="grid grid-cols-[2.5rem_10rem_1fr] items-baseline gap-x-5 rounded-[var(--radius-lg)] border border-iris/40 bg-bloom/50 px-6 py-5 transition-colors hover:bg-bloom"
            >
              <span
                className={
                  row.trust === "cryptographic" ? "text-intaglio" : "text-iris-ink"
                }
              >
                <TrustMark trust={row.trust} size={22} />
              </span>
              <span className="text-[length:var(--text-evidence)] font-semibold">
                {row.name}
              </span>
              <span>
                <span className="block">{row.example}</span>
                <span className="mt-1 block text-label text-iris-ink">
                  {row.certainty}
                </span>
              </span>
            </li>
          ))}
        </ol>

        <p className="mt-8 max-w-[38rem] text-iris-ink">
          A cryptographic pass suppresses probabilistic disputes about the
          fields it signed. A blurred capture is <em>inconclusive</em>, which
          counts against coverage — it is never treated as a pass. Below seventy
          per cent coverage the verdict cannot be green, whatever the score.
        </p>
      </div>

      {/* ---------------------------------------------------------- budget */}
      <div className="bg-bloom/60">
        <Section title="Where the second goes">
          <p className="mt-6 max-w-[38rem] text-iris-ink">
            Measured on an eight-core CPU with no GPU. Deterministic checks run
            first, so a hard failure returns before the vision stack is touched.
            Deep forensics fire only when the risk gate escalates, which is
            about fifteen per cent of documents.
          </p>

          <ul className="mt-8 space-y-1">
            {PIPELINE.map((s) => (
              <li key={s.stage} className="flex items-center gap-4 py-2">
                <span className="w-72 shrink-0 text-[length:var(--text-body)]">{s.stage}</span>
                <span
                  className="h-3 rounded-full bg-guilloche/70"
                  style={{ width: `${(s.ms / widest) * 100}%`, maxWidth: "22rem" }}
                />
                <span className="data text-label text-iris-ink">{s.ms} ms</span>
              </li>
            ))}
          </ul>

          <div className="mt-6 border-t border-iris/60 pt-4">
            <span className="data text-[length:var(--text-evidence)] font-semibold">
              {total} ms
            </span>{" "}
            <span className="text-iris-ink">
              for the tier that runs on every document. The first verdict is on
              screen well before that, because results stream as each module
              finishes.
            </span>
          </div>
        </Section>
      </div>

      {/* ---------------------------------------------------------- limits */}
      <Section title="What it does not do">
        <p className="mt-6 max-w-[38rem] text-iris-ink">
          Stated here rather than waiting to be asked.
        </p>
        <ul className="mt-6 max-w-[42rem] grid gap-4">
          {LIMITS.map((l) => (
            <li key={l} className="rounded-[var(--radius-md)] border border-iris/40 bg-bloom/30 p-5 text-iris-ink">
              {l}
            </li>
          ))}
        </ul>
      </Section>

      {/* ------------------------------------------------------------ exit */}
      <div className="bg-intaglio px-8 py-16 text-paper">
        <div className="mx-auto max-w-5xl">
          <p className="max-w-[34rem] text-[length:var(--text-screen)] leading-snug">
            No internet. No GPU. Eight cores. That is what a border post at
            Raxaul actually has.
          </p>
          <Link
            to="/capture"
            className="mt-8 inline-block rounded-[var(--radius-md)] bg-guilloche px-6 py-3 font-medium text-white hover:bg-guilloche/90 transition-colors"
          >
            Open the console
          </Link>
        </div>
      </div>
    </div>
  );
}
