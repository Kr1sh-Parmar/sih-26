"""Scene 3 over a real HTTP + WebSocket connection to a running uvicorn.

Scan a signed Aadhaar and a PAN in one session. The signed Aadhaar payload
gives 1996; the PAN prints 1998. Hard fail with cryptographic backing.
"""
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import httpx
import websockets

PORT = os.environ.get("SCREENING_PORT", "8000")
BASE = f"http://127.0.0.1:{PORT}"
WS = f"ws://127.0.0.1:{PORT}"
SESSION = f"scene3-{uuid.uuid4().hex[:8]}"
COLOUR = {"GREEN": "\033[32m", "AMBER": "\033[33m", "RED": "\033[31m"}


async def screen(client, path: Path, doc_type: str) -> dict:
    with path.open("rb") as fh:
        r = await client.post(
            f"{BASE}/screen",
            files={"image": (path.name, fh, "image/png")},
            data={"doc_type": doc_type, "session_id": SESSION},
        )
    r.raise_for_status()
    screening = r.json()

    print(f"\n=== {doc_type.upper()} " + "=" * (60 - len(doc_type)))
    verdict = None
    async with websockets.connect(f"{WS}/screen/{screening['id']}") as socket:
        while True:
            message = json.loads(await socket.recv())
            kind = message["type"]
            if kind == "signal":
                s = message["signal"]
                if s["verdict"] in ("pass", "fail"):
                    mark = "OK " if s["verdict"] == "pass" else "!! "
                    print(f"  {mark}[{s['trust_class'][:6]:6}] {s['evidence']}")
            elif kind == "verdict":
                verdict = message
            elif kind == "phase" and message["phase"] == "done":
                break

    band = verdict["band"]
    print(f"\n  {COLOUR[band]}{band}\033[0m  score {verdict['score']:.2f}  "
          f"coverage {verdict['coverage']:.2f}")
    if verdict.get("reason"):
        print(f"  reason: {verdict['reason']}")
    if verdict.get("disclosure"):
        print(f"  disclosure: {verdict['disclosure']}")
    return screening


async def main() -> int:
    demo = Path(__file__).resolve().parents[1] / "var" / "demo"
    async with httpx.AsyncClient(timeout=30) as client:
        await screen(client, demo / "aadhaar.qr.png", "aadhaar")
        pan = await screen(client, demo / "pan.qr.png", "pan")

        doc = (await client.get(f"{BASE}/screen/{pan['id']}/doc")).json()
        print("\n=== PAN fields the console will render " + "=" * 22)
        for f in doc["fields"]:
            print(f"  {f['name']:18} {f['value']:26} via {f['source']}")

        session = (await client.get(f"{BASE}/sessions/{SESSION}")).json()
        print("\n=== session " + "=" * 49)
        for d in session["documents"]:
            print(f"  {d['doc_type']:10} {d['band']:6} score {d['score']:.2f} "
                  f"coverage {d['coverage']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
