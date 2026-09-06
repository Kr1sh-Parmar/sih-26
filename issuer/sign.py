"""Reference issuance authority. OUT-OF-BAND TOOLING.

Nothing under `api/`, `modules/` or `fusion/` may import this package - it is
enforced by a test. A real issuing authority is not reachable from a border
checkpoint, and neither is this one. It deposits public keys into the trust
anchor store during setup and is never called at inspection time (D2).

Why it exists at all: four of six Indian identity documents carry no
cryptographic integrity whatsoever, so a verifier has no technical means of
confirming them. That is a real national gap, not a limitation of this project.
This tool demonstrates signed verification end to end. The signatures are ours
and the console says so.
"""
import base64
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

from core.canonical import FIELD_ORDER, canonicalise

DEFAULT_ISSUER_ID = "SIH-REF-01"


@dataclass(frozen=True)
class Keypair:
    issuer_id: str
    private_key: bytes
    public_key: bytes

    @classmethod
    def generate(cls, issuer_id: str = DEFAULT_ISSUER_ID) -> "Keypair":
        sk = Ed25519PrivateKey.generate()
        return cls(
            issuer_id=issuer_id,
            private_key=sk.private_bytes_raw(),
            public_key=sk.public_key().public_bytes_raw(),
        )

    def save(self, directory: Path) -> Path:
        """Private key to disk. `*.key` is gitignored - keep it that way."""
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.issuer_id}.key"
        path.write_bytes(self.private_key)
        (directory / f"{self.issuer_id}.pub").write_bytes(self.public_key)
        return path

    @classmethod
    def load(cls, directory: Path, issuer_id: str = DEFAULT_ISSUER_ID) -> "Keypair":
        private = (directory / f"{issuer_id}.key").read_bytes()
        sk = Ed25519PrivateKey.from_private_bytes(private)
        return cls(issuer_id, private, sk.public_key().public_bytes_raw())


def sign(payload: dict, keypair: Keypair) -> str:
    """Canonicalise, sign, and return the envelope that goes into the QR.

    The envelope carries the issuer *id*, never the key. The verifier looks the
    key up in its own trust anchor store, so a forger who mints their own
    keypair and embeds the public half gets UNKNOWN_ISSUER, not AUTHENTIC.
    """
    unknown = set(payload) - set(FIELD_ORDER)
    if unknown:
        raise ValueError(f"refusing to sign unknown fields {sorted(unknown)}")

    signed = dict(payload)
    signed["issuer_id"] = keypair.issuer_id
    sk = Ed25519PrivateKey.from_private_bytes(keypair.private_key)
    signature = sk.sign(canonicalise(signed))

    return json.dumps(
        {
            "issuer_id": keypair.issuer_id,
            "payload": {k: payload.get(k) for k in FIELD_ORDER if payload.get(k)},
            "signature": base64.b64encode(signature).decode("ascii"),
        },
        separators=(",", ":"),
        ensure_ascii=False,
        sort_keys=True,
    )


def public_key_of(private_key: bytes) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(private_key).public_key().public_bytes_raw()


def check_public_bytes(raw: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(raw)
        return True
    except Exception:
        return False
