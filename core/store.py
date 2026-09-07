"""Persistence. context/CONTRACTS.md section 8.

SQLite, stdlib only. The schema is the one in the contract; the engine is not,
and that is deliberate - a checkpoint box should not need a database server
running to screen a document. Everything that would eventually want Postgres is
funnelled through this one module, so the swap is a one-file change. The single
thing SQLite genuinely cannot do here is pgvector's HNSW index, and 1:N gallery
search is Tier 2 and cut-list item 5.

Two rules that are not negotiable:

  * Never store a raw identity number. Salted hash plus the last four digits,
    in fixtures and tests too.
  * Store the FULL signal list, not the evidence cards. Cards are a view. If a
    weight changes you must be able to re-score a historical case without
    re-running inference.
"""
import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from core.trust import Anchor, TrustAnchorStore
from fusion.signal import Signal, to_json

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "var" / "screening.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS screening_events (
  id              TEXT PRIMARY KEY,
  session_id      TEXT NOT NULL,
  doc_type        TEXT NOT NULL,
  doc_hash        TEXT NOT NULL,
  id_number_hash  TEXT,
  id_number_last4 TEXT,
  verdict         TEXT NOT NULL,
  score           REAL,
  coverage        REAL,
  signals         TEXT NOT NULL,
  model_versions  TEXT NOT NULL,
  officer_id      TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_events_session ON screening_events(session_id);
CREATE INDEX IF NOT EXISTS ix_events_idhash  ON screening_events(id_number_hash);

CREATE TABLE IF NOT EXISTS trust_anchors (
  issuer_id    TEXT PRIMARY KEY,
  public_key   BLOB NOT NULL,
  algorithm    TEXT NOT NULL,
  is_reference INTEGER NOT NULL,
  valid_from   TEXT,
  valid_until  TEXT
);

CREATE TABLE IF NOT EXISTS face_gallery (
  id         TEXT PRIMARY KEY,
  event_id   TEXT REFERENCES screening_events(id),
  embedding  BLOB NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS watchlist (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  source      TEXT,
  name        TEXT,
  name_key    TEXT,
  aliases     TEXT,
  dob         TEXT,
  nationality TEXT,
  doc_numbers TEXT
);
CREATE INDEX IF NOT EXISTS ix_watchlist_key ON watchlist(name_key);
CREATE INDEX IF NOT EXISTS ix_watchlist_doc ON watchlist(doc_numbers);
"""


def _salt() -> bytes:
    """Pepper for identity-number hashing.

    Set SCREENING_ID_SALT in deployment. The dev fallback is written once to a
    gitignored file so hashes stay stable across restarts on one machine and do
    not silently become a plain SHA-256 of a 12-digit number, which is
    trivially reversible by brute force.
    """
    env = os.environ.get("SCREENING_ID_SALT")
    if env:
        return env.encode("utf-8")
    path = ROOT / "var" / "id_salt.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(os.urandom(32))
    return path.read_bytes()


def hash_id_number(number: str | None) -> tuple[str | None, str | None]:
    """Raw identity number to (salted hash, last four). The raw value stops here."""
    if not number:
        return None, None
    digits = "".join(c for c in str(number) if c.isalnum())
    if not digits:
        return None, None
    h = hashlib.sha256(_salt() + digits.encode("utf-8")).hexdigest()
    return h, digits[-4:]


class Store:
    def __init__(self, path: Path | str = DEFAULT_DB):
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    @contextmanager
    def _tx(self):
        with self._conn:
            yield self._conn

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------- anchors

    def put_anchor(self, anchor: Anchor) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO trust_anchors "
                "(issuer_id, public_key, algorithm, is_reference, valid_from, valid_until) "
                "VALUES (?,?,?,?,?,?)",
                (anchor.issuer_id, anchor.public_key, anchor.algorithm,
                 int(anchor.is_reference), anchor.valid_from, anchor.valid_until),
            )

    def trust_anchors(self) -> TrustAnchorStore:
        rows = self._conn.execute("SELECT * FROM trust_anchors").fetchall()
        return TrustAnchorStore([
            Anchor(r["issuer_id"], bytes(r["public_key"]), r["algorithm"],
                   bool(r["is_reference"]), r["valid_from"], r["valid_until"])
            for r in rows
        ])

    # -------------------------------------------------------------- events

    def record_event(self, *, session_id: str, doc_type: str, doc_hash: str,
                     verdict: str, score: float, coverage: float,
                     signals: list[Signal], model_versions: dict,
                     id_number: str | None = None, officer_id: str | None = None) -> str:
        event_id = str(uuid.uuid4())
        id_hash, last4 = hash_id_number(id_number)
        with self._tx() as c:
            c.execute(
                "INSERT INTO screening_events (id, session_id, doc_type, doc_hash, "
                "id_number_hash, id_number_last4, verdict, score, coverage, signals, "
                "model_versions, officer_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (event_id, session_id, doc_type, doc_hash, id_hash, last4, verdict,
                 score, coverage, json.dumps([to_json(s) for s in signals]),
                 json.dumps(model_versions, sort_keys=True), officer_id),
            )
        return event_id

    def event(self, event_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM screening_events WHERE id = ?", (event_id,)
        ).fetchone()
        return self._event_row(row) if row else None

    def session_events(self, session_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM screening_events WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        return [self._event_row(r) for r in rows]

    def recent_events(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Newest first, for the audit table.

        Deliberately returns the full row, signal list included. The console
        opens an event to show what was recorded, and the whole premise of
        storing signals rather than cards is that the record is sufficient on
        its own. Trimming it here would mean a second round trip to prove that.
        """
        rows = self._conn.execute(
            "SELECT * FROM screening_events ORDER BY created_at DESC, id DESC "
            "LIMIT ? OFFSET ?",
            (max(1, min(int(limit), 500)), max(0, int(offset))),
        ).fetchall()
        return [self._event_row(r) for r in rows]

    def count_events(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM screening_events").fetchone()[0]

    @staticmethod
    def _event_row(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["signals"] = json.loads(d["signals"])
        d["model_versions"] = json.loads(d["model_versions"])
        return d

    def seen_document_number(self, id_number: str, exclude_session: str | None = None) -> list[dict]:
        """Prior screenings of the same identity number, by hash. Layer F input."""
        h, _ = hash_id_number(id_number)
        if not h:
            return []
        sql = "SELECT * FROM screening_events WHERE id_number_hash = ?"
        args: list = [h]
        if exclude_session:
            sql += " AND session_id != ?"
            args.append(exclude_session)
        return [self._event_row(r) for r in self._conn.execute(sql, args).fetchall()]

    # ------------------------------------------------------------- gallery

    def add_face(self, event_id: str, embedding: np.ndarray) -> str:
        face_id = str(uuid.uuid4())
        vec = np.asarray(embedding, dtype=np.float32).ravel()
        with self._tx() as c:
            c.execute("INSERT INTO face_gallery (id, event_id, embedding) VALUES (?,?,?)",
                      (face_id, event_id, vec.tobytes()))
        return face_id

    def search_faces(self, embedding: np.ndarray, threshold: float,
                     limit: int = 5) -> list[tuple[str, str, float]]:
        """Brute-force cosine over the gallery. Returns (face_id, event_id, cosine).

        ponytail: O(n) scan. Swap in pgvector HNSW when the gallery outgrows a
        few thousand rows - at 512 floats a row that is still single-digit
        milliseconds, and 1:N only runs on escalated documents.
        """
        query = np.asarray(embedding, dtype=np.float32).ravel()
        norm = np.linalg.norm(query)
        if norm == 0:
            return []
        query = query / norm

        hits = []
        for row in self._conn.execute("SELECT id, event_id, embedding FROM face_gallery"):
            vec = np.frombuffer(row["embedding"], dtype=np.float32)
            n = np.linalg.norm(vec)
            if n == 0:
                continue
            cos = float(np.dot(query, vec / n))
            if cos >= threshold:
                hits.append((row["id"], row["event_id"], cos))
        hits.sort(key=lambda h: -h[2])
        return hits[:limit]

    # ----------------------------------------------------------- watchlist

    def add_watchlist_entry(self, *, source: str, name: str, name_key: str,
                            aliases: list[str] | None = None, dob: str | None = None,
                            nationality: str | None = None,
                            doc_numbers: list[str] | None = None) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT INTO watchlist (source, name, name_key, aliases, dob, "
                "nationality, doc_numbers) VALUES (?,?,?,?,?,?,?)",
                (source, name, name_key, json.dumps(aliases or []), dob, nationality,
                 json.dumps(doc_numbers or [])),
            )

    def watchlist_by_name_key(self, name_key: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM watchlist WHERE name_key = ?", (name_key,)
        ).fetchall()
        return [dict(r) for r in rows]

    def watchlist_by_document(self, number: str) -> list[dict]:
        needle = f'"{number.upper()}"'
        rows = self._conn.execute(
            "SELECT * FROM watchlist WHERE doc_numbers LIKE ?", (f"%{needle}%",)
        ).fetchall()
        return [dict(r) for r in rows]

    def watchlist_size(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
