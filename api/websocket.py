"""The streaming protocol. Mirrors frontend/src/contracts/events.ts exactly.

The console reducer switches on these type strings, so this file and that one
have to agree or the UI silently drops events. The union is:

    {type: "phase",    phase}
    {type: "signal",   signal}
    {type: "findings", findings}
    {type: "verdict",  band, score, coverage, disclosure}
    {type: "error",    message, recoverable}

Streaming is nearly free and it transforms perceived latency: the officer sees
validation land at roughly 300 ms rather than waiting a second for everything
(TECHNICAL-SPEC.md section 3).
"""
import asyncio
from typing import Iterator

from api.router import Event
from fusion.finding import finding_to_json
from fusion.signal import to_json

#: Artificial pacing so the console renders a stream rather than a single dump.
#: These come from the latency budget, and they only apply when the real work
#: finished faster than the budget - never as an added delay on a slow run.
PACE_MS = {"extraction": 40, "validation": 12, "tamper": 30, "face": 45}


def encode(event: Event) -> dict | None:
    """One pipeline event to one wire message, or None if it is internal."""
    if event.type == "phase":
        return {"type": "phase", "phase": event.payload["phase"]}

    if event.type == "signal":
        return {"type": "signal", "signal": to_json(event.payload["signal"])}

    if event.type == "findings":
        return {"type": "findings",
                "findings": [finding_to_json(f) for f in event.payload["findings"]]}

    if event.type == "verdict":
        # `reason` is extra to the frontend contract. Additive keys are safe -
        # the reducer reads named fields - and the audit log wants it.
        return {
            "type": "verdict",
            "band": event.payload["band"],
            "score": event.payload["score"],
            "coverage": event.payload["coverage"],
            "disclosure": event.payload["disclosure"],
            "reason": event.payload.get("reason"),
        }

    if event.type == "cards":
        return {"type": "cards", "cards": event.payload["cards"]}

    # "done" carries the Result object for the caller to persist. Internal.
    return None


def error(message: str, recoverable: bool = True) -> dict:
    return {"type": "error", "message": message, "recoverable": recoverable}


async def stream(events: Iterator[Event], send, *, paced: bool = True,
                 on_done=None) -> None:
    """Push a pipeline run down a socket, pacing so the list writes itself in."""
    last_module = None
    for event in events:
        if event.type == "done":
            if on_done:
                on_done(event.payload)
            continue

        message = encode(event)
        if message is None:
            continue

        if paced and event.type == "signal":
            module = event.payload["signal"].module
            if module != last_module:
                await asyncio.sleep(PACE_MS.get(module, 20) / 1000)
                last_module = module
            else:
                await asyncio.sleep(0.006)
        await send(message)
