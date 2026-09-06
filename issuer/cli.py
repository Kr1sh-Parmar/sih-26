"""Reference issuer command line. OUT-OF-BAND - run at setup, never at inspection.

    python -m issuer.cli init                    generate a keypair, seed the store
    python -m issuer.cli mint demo/aadhaar.json  sign a payload, write a QR

The mint step writes three files next to the payload: the signed envelope, the
QR image, and a copy of the payload with the fields as printed. That last one
is what makes a forgery test possible - edit the printed copy, leave the
envelope alone, and you have reproduced the exact fraud this system exists to
catch.
"""
import argparse
import json
import sys
from pathlib import Path

from core.canonical import doc_hash
from core.store import DEFAULT_DB, Store
from core.trust import Anchor
from issuer.qr import encode
from issuer.sign import DEFAULT_ISSUER_ID, Keypair, sign

ROOT = Path(__file__).resolve().parents[1]
KEY_DIR = ROOT / "var" / "issuer"


def cmd_init(args) -> int:
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    key_path = KEY_DIR / f"{args.issuer_id}.key"
    if key_path.exists() and not args.force:
        keypair = Keypair.load(KEY_DIR, args.issuer_id)
        print(f"reusing existing keypair for {args.issuer_id} (pass --force to replace)")
    else:
        keypair = Keypair.generate(args.issuer_id)
        keypair.save(KEY_DIR)
        print(f"generated Ed25519 keypair for {args.issuer_id} -> {key_path}")

    store = Store(args.db)
    store.put_anchor(Anchor(
        issuer_id=keypair.issuer_id,
        public_key=keypair.public_key,
        algorithm="ed25519",
        # Always true here. This flag is what makes the console show the
        # disclosure string; a real issuer key would be added with False.
        is_reference=True,
    ))
    print(f"public key deposited in the trust anchor store at {args.db}")
    print("is_reference=true, so the console will label every verification "
          "against it as a demonstration")
    return 0


def cmd_mint(args) -> int:
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    keypair = Keypair.load(KEY_DIR, args.issuer_id)

    envelope = sign(payload, keypair)
    out = Path(args.out) if args.out else Path(args.payload).with_suffix("")
    out.parent.mkdir(parents=True, exist_ok=True)

    envelope_path = out.with_name(out.name + ".signed.json")
    envelope_path.write_text(envelope, encoding="utf-8")
    qr_path = encode(envelope, out.with_name(out.name + ".qr.png"))

    print(f"signed  {envelope_path}")
    print(f"qr      {qr_path}  ({len(envelope)} bytes of payload)")
    print(f"hash    {doc_hash({**payload, 'issuer_id': keypair.issuer_id})}")
    return 0


def cmd_anchors(args) -> int:
    store = Store(args.db)
    anchors = store.trust_anchors()
    if not len(anchors):
        print("trust anchor store is empty - run `python -m issuer.cli init` first")
        return 1
    for issuer_id, anchor in anchors._by_id.items():
        kind = "reference (demonstration)" if anchor.is_reference else "production"
        print(f"{issuer_id:14} {anchor.algorithm:8} {kind}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="issuer", description=__doc__)
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--issuer-id", default=DEFAULT_ISSUER_ID)
    sub = p.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="generate a keypair and seed the trust anchor store")
    init.add_argument("--force", action="store_true", help="replace an existing keypair")
    init.set_defaults(func=cmd_init)

    mint = sub.add_parser("mint", help="sign a payload and write its QR")
    mint.add_argument("payload", help="JSON file of document fields")
    mint.add_argument("--out", help="output basename (default: alongside the payload)")
    mint.set_defaults(func=cmd_mint)

    anchors = sub.add_parser("anchors", help="list the trust anchor store")
    anchors.set_defaults(func=cmd_anchors)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
