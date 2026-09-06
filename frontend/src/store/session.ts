/**
 * A screening session: every document one traveller presents at the counter.
 *
 * This is what makes cross-document trust propagation possible
 * (context/CONTRACTS.md §2, `prior_docs`). When one document in the session is
 * signed, its payload becomes ground truth for the others — which is the
 * headline claim of the whole project, because four of six Indian identity
 * documents carry no cryptographic integrity today.
 */
import { create } from "zustand";
import type { Band } from "../contracts";

export interface SessionDocument {
  id: string;
  docType: string;
  label: string;
  signed: boolean;
  band: Band | null;
  /** Fixture key, so a document can be re-opened on the screening screen. */
  fixture: string;
}

/** One field the signed document vouches for, and whether the other agrees. */
export interface PropagationEdge {
  field: string;
  from: string;
  to: string;
  fromValue: string;
  toValue: string;
  agrees: boolean;
}

interface SessionState {
  sessionId: string;
  documents: SessionDocument[];
  edges: PropagationEdge[];
  activeField: string | null;

  start: (id?: string) => void;
  add: (doc: SessionDocument) => void;
  setEdges: (edges: PropagationEdge[]) => void;
  setActiveField: (field: string | null) => void;
  clear: () => void;
}

const newId = () =>
  `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;

export const useSession = create<SessionState>((set) => ({
  sessionId: newId(),
  documents: [],
  edges: [],
  activeField: null,

  start: (id) => set({ sessionId: id ?? newId(), documents: [], edges: [] }),
  add: (doc) =>
    set((s) =>
      s.documents.some((d) => d.id === doc.id)
        ? s
        : { documents: [...s.documents, doc] },
    ),
  setEdges: (edges) => set({ edges }),
  setActiveField: (activeField) => set({ activeField }),
  clear: () => set({ documents: [], edges: [], activeField: null }),
}));
