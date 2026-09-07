/**
 * Which reality is on screen.
 *
 * An officer must never be unsure whether they are looking at a real screening
 * or a rehearsed one. This is not a status light — a fixture verdict mistaken
 * for a live one is the single worst thing this console could do, so the
 * fixture state is stated in words, in the officer's own vocabulary, and it is
 * the louder of the two.
 */
import type { Mode } from "../transport/mode";
import { cn } from "../lib/utils";

export function ModeBadge({ mode, className }: { mode: Mode; className?: string }) {
  if (mode === "probing") {
    return (
      <span className={cn("text-label text-iris-ink", className)}>
        Checking for the screening service…
      </span>
    );
  }

  if (mode === "live") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-2 border border-iris px-2.5 py-1 text-label text-iris-ink",
          className,
        )}
      >
        <span aria-hidden className="size-1.5 rounded-full bg-clear" />
        Live screening service
      </span>
    );
  }

  return (
    <span
      role="status"
      className={cn(
        "inline-flex items-center gap-2 border-2 border-secondary-ink bg-guilloche/40 px-2.5 py-1 text-label font-medium text-secondary-ink",
        className,
      )}
    >
      <span aria-hidden className="size-1.5 rounded-full bg-secondary-ink" />
      Rehearsed case — not a live screening
    </span>
  );
}
