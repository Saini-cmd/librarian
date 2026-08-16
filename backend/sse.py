"""Shared Server-Sent-Events helpers for the long-running endpoints.

Both `/api/process` and `/sync` stream `{type, ...}` JSON payloads as SSE via a
`queue.Queue` with a `: ping` heartbeat; these helpers keep the two endpoints'
wiring identical.
"""

import json
from queue import Empty, Queue

from fastapi.responses import StreamingResponse


def sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def sse_response(events: list[dict]) -> StreamingResponse:
    def gen():
        for event in events:
            yield sse(event)

    return StreamingResponse(gen(), media_type="text/event-stream")


def stream_queue(progress_q: Queue):
    """Yield SSE events from a queue until a `done` event, with a ping heartbeat."""
    while True:
        try:
            event = progress_q.get(timeout=10)
        except Empty:
            yield ": ping\n\n"
            continue
        yield sse(event)
        if event.get("done"):
            break
