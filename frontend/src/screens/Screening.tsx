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
import { useScreening } from "../store/screening";
import { fixture, replayFixture, type FixtureName } from "../transport/mockSocket";
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

  const s = useScreening();

  useEffect(() => {
    s.reset();
    const doc = fixture(scene);
    s.setDoc(doc);
    startedAt.current = performance.now();
    setElapsed(null);

    const run = replayFixture(scene, (e) => {
      s.apply(e);
      if (e.type === "phase" && e.phase === "done") {
        setElapsed(Math.round(performance.now() - startedAt.current));
      }
    });
    return () => run.cancel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene]);

  const doc = s.doc;
  const canvas = (doc?.meta.canvas as [number, number]) ?? [1654, 1170];

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-8 px-8 py-6 lg:grid-cols-[minmax(0,2fr)_minmax(26rem,1fr)]">
      {/* ---------------------------------------------- physical evidence */}
      <div className="min-w-0">
        <StreamStatus phase={s.phase} signals={s.signals} elapsedMs={elapsed} />

        <div className="mt-4">
          {doc && (
            <DocumentViewer
              docType={doc.meta.doc_type}
              canvas={canvas}
              fields={doc.fields}
              signals={s.signals}
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

        {/* Scene picker. Replaced by the capture screen once a scanner is
            wired in; kept because DEMO.md wants a rehearsed running order. */}
        <div className="mt-10 border-t border-iris pt-4">
          <p className="text-label text-iris-ink">Replay a rehearsed case</p>
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
        </div>
      </div>
    </div>
  );
}
