/**
 * Generic UI icons, drawn in the same hand-rolled language as the trust
 * marks in `TrustMark.tsx` (16x16 box, `currentColor`, no icon package).
 *
 * These replace two things that don't belong here: raw emoji (renders
 * differently per OS/browser, and doesn't match the geometric mark
 * language) and literal Unicode glyphs used as icons (the `▶` expand
 * triangle).
 */
import type { MarkProps } from "./TrustMark";

/** A flatbed scanner: open lid, bed, and a scan line. */
export function ScannerIcon({ size = 16, className }: MarkProps) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} className={className}
         aria-hidden="true" fill="none" stroke="currentColor">
      <path d="M4 1.5 H12 L14.5 4 H1.5 Z" strokeWidth="1" strokeLinejoin="round" />
      <rect x="1.5" y="4" width="13" height="8.5" rx="1" strokeWidth="1.1" />
      <path d="M3 8.2 H13" strokeWidth="1" strokeDasharray="1.6 1.6" />
    </svg>
  );
}

/** A file, ready to be handed over — an upward arrow into an open tray. */
export function UploadIcon({ size = 16, className }: MarkProps) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} className={className}
         aria-hidden="true" fill="none" stroke="currentColor">
      <path d="M8 10.5 V2 M5 5 L8 2 L11 5" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M2 10.5 V13.2 a1 1 0 0 0 1 1 H13 a1 1 0 0 0 1-1 V10.5"
            strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** A camera: rounded body, viewfinder bump, lens. */
export function CameraIcon({ size = 16, className }: MarkProps) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} className={className}
         aria-hidden="true" fill="none" stroke="currentColor">
      <path d="M2 5.5 h2.2 l1-1.5 h5.6 l1 1.5 H14 a1 1 0 0 1 1 1 V12.5 a1 1 0 0 1-1 1 H2 a1 1 0 0 1-1-1 V6.5 a1 1 0 0 1 1-1 Z"
            strokeWidth="1.1" strokeLinejoin="round" />
      <circle cx="8" cy="9" r="2.6" strokeWidth="1.1" />
    </svg>
  );
}

/** The capture action — an aperture, distinct from the camera body itself. */
export function ShutterIcon({ size = 16, className }: MarkProps) {
  const ticks = Array.from({ length: 6 }, (_, i) => i * 60);
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} className={className}
         aria-hidden="true" fill="none" stroke="currentColor">
      <circle cx="8" cy="8" r="5.6" strokeWidth="1.1" />
      {ticks.map((deg) => (
        <line key={deg} x1="8" y1="1.4" x2="8" y2="3" strokeWidth="1.2"
              strokeLinecap="round" transform={`rotate(${deg} 8 8)`} />
      ))}
    </svg>
  );
}

/** Retake — an open arc with an arrowhead, reading as "go again." */
export function RetakeIcon({ size = 16, className }: MarkProps) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} className={className}
         aria-hidden="true" fill="none" stroke="currentColor">
      <path d="M12.8 8 a4.8 4.8 0 1 1 -1.4 -3.4" strokeWidth="1.3" strokeLinecap="round" />
      <path d="M11.4 1.8 L11.4 4.6 L14.2 4.6" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Pass. */
export function CheckIcon({ size = 16, className }: MarkProps) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} className={className}
         aria-hidden="true" fill="none" stroke="currentColor">
      <path d="M3.5 8.5 L6.5 11.5 L12.5 4.5" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Fail. */
export function CrossIcon({ size = 16, className }: MarkProps) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} className={className}
         aria-hidden="true" fill="none" stroke="currentColor">
      <path d="M4 4 L12 12 M12 4 L4 12" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

/** Expand/collapse. The caller rotates it (0deg closed, 90deg open). */
export function ChevronIcon({ size = 16, className }: MarkProps) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} className={className}
         aria-hidden="true" fill="none" stroke="currentColor">
      <path d="M5.5 3 L10.5 8 L5.5 13" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
