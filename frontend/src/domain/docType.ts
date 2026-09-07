/**
 * What an officer calls each document.
 *
 * `passport` is a wire value; "Passport" is what goes on screen. The backend
 * has the same map in `core/profiles.py:label()` and the two are allowed to
 * drift only in wording, never in which six types exist — `DOC_TYPES` is the
 * frozen set.
 */
const LABEL: Record<string, string> = {
  passport: "Passport",
  visa: "Visa",
  aadhaar: "Aadhaar card",
  pan: "PAN card",
  voter_id: "Voter ID",
  dl: "Driving licence",
};

/** Falls through to the wire value: an unknown type is better shown than hidden. */
export function docLabel(docType: string): string {
  return LABEL[docType] ?? docType;
}
