"""Trust anchor store and signature verification. Screening side only.

The store maps an issuer id to a public key. A payload names its issuer; it
never carries the key. Trusting a key supplied inside the thing it is meant to
authenticate is the oldest mistake in the book, so `verify_payload` looks the
issuer up and refuses anything it does not already hold.

`is_reference` is what drives the console disclosure string. A verification
against our own reference issuer must never be presented as a government one
(CONTEXT.md section 5).
"""
import base64
import json
from dataclasses import dataclass
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.canonical import canonicalise

#: The eight states a validation can end in. `NO_CRYPTO_ANCHOR` is the honest
#: one for a document with no verifiable signature - never silently a pass.
State = Literal[
    "AUTHENTIC", "TAMPERED", "INVALID_SIGNATURE", "UNKNOWN_ISSUER",
    "REVOKED", "EXPIRED", "MALFORMED_PAYLOAD", "NO_CRYPTO_ANCHOR",
]


@dataclass(frozen=True)
class Anchor:
    issuer_id: str
    public_key: bytes
    algorithm: str
    is_reference: bool
    valid_from: str | None = None
    valid_until: str | None = None


@dataclass(frozen=True)
class Verification:
    state: State
    issuer_id: str | None
    is_reference: bool
    payload: dict
    detail: str

    @property
    def ok(self) -> bool:
        return self.state == "AUTHENTIC"


class TrustAnchorStore:
    """Keyed by issuer id. Backed by core.store in production, in-memory in tests."""

    def __init__(self, anchors: list[Anchor] | None = None):
        self._by_id = {a.issuer_id: a for a in (anchors or [])}

    def add(self, anchor: Anchor) -> None:
        self._by_id[anchor.issuer_id] = anchor

    def get(self, issuer_id: str) -> Anchor | None:
        return self._by_id.get(issuer_id)

    def __len__(self) -> int:
        return len(self._by_id)


def unpack(blob: str) -> dict:
    """A QR payload string to its parts. Raises ValueError on anything odd."""
    data = json.loads(blob)
    if not isinstance(data, dict):
        raise ValueError("payload is not an object")
    for key in ("issuer_id", "payload", "signature"):
        if key not in data:
            raise ValueError(f"payload is missing {key!r}")
    return data


def verify_payload(blob: str, store: TrustAnchorStore, now=None) -> Verification:
    """Verify a signed document payload against the trust anchor store."""
    try:
        envelope = unpack(blob)
    except (ValueError, json.JSONDecodeError) as exc:
        return Verification("MALFORMED_PAYLOAD", None, False, {},
                            f"The signed payload could not be read: {exc}")

    issuer_id = str(envelope["issuer_id"])
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        return Verification("MALFORMED_PAYLOAD", issuer_id, False, {},
                            "The signed payload is not a set of document fields")

    anchor = store.get(issuer_id)
    if anchor is None:
        return Verification(
            "UNKNOWN_ISSUER", issuer_id, False, payload,
            f"Issuer {issuer_id} is not present in the trust anchor store",
        )
    if anchor.algorithm != "ed25519":
        return Verification("INVALID_SIGNATURE", issuer_id, anchor.is_reference, payload,
                            f"Issuer {issuer_id} uses unsupported algorithm {anchor.algorithm}")

    if anchor.valid_until and now and str(now) > anchor.valid_until:
        return Verification("REVOKED", issuer_id, anchor.is_reference, payload,
                            f"The signing key for issuer {issuer_id} is no longer valid")

    signed = dict(payload)
    signed["issuer_id"] = issuer_id
    try:
        message = canonicalise(signed)
    except ValueError as exc:
        return Verification("MALFORMED_PAYLOAD", issuer_id, anchor.is_reference, payload,
                            f"The signed payload could not be canonicalised: {exc}")

    try:
        signature = base64.b64decode(envelope["signature"], validate=True)
    except Exception:
        return Verification("MALFORMED_PAYLOAD", issuer_id, anchor.is_reference, payload,
                            "The signature is not valid base64")

    try:
        Ed25519PublicKey.from_public_bytes(anchor.public_key).verify(signature, message)
    except InvalidSignature:
        # The signature is well formed but does not match these fields, which
        # means the fields were changed after signing.
        return Verification(
            "TAMPERED", issuer_id, anchor.is_reference, payload,
            f"The document fields do not match the signature issued by {issuer_id}",
        )
    except Exception as exc:
        return Verification("INVALID_SIGNATURE", issuer_id, anchor.is_reference, payload,
                            f"The signature could not be checked: {exc}")

    kind = "reference issuer" if anchor.is_reference else "issuer"
    return Verification(
        "AUTHENTIC", issuer_id, anchor.is_reference, payload,
        f"Ed25519 signature verifies against trusted {kind} {issuer_id}",
    )
