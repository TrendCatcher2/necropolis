"""In-process job events: exhume (and later probe) progress -> JobBus -> SSE (graveyard-ui spec).

Events carry counts, phases and endpoint keys only: never a response body, a raw URL or a query value
(safety.md rule 5).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Literal

from pydantic import BaseModel, ConfigDict

EventType = Literal["progress", "endpoint", "done", "error"]


class JobEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str
    type: EventType
    data: dict[str, object]


class JobBus:
    """Fan-out of each job's events to its subscribers. A subscriber that stops reading misses events rather than
    growing memory; the UI then fetches the job state (graveyard-ui Req 1.2)."""

    MAX_QUEUE = 10_000

    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[JobEvent]]] = {}

    def publish(self, event: JobEvent) -> None:
        for queue in tuple(self._queues.get(event.job_id, ())):
            with suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    @contextmanager
    def subscribe(self, job_id: str) -> Iterator[asyncio.Queue[JobEvent]]:
        queue: asyncio.Queue[JobEvent] = asyncio.Queue(maxsize=self.MAX_QUEUE)
        self._queues.setdefault(job_id, set()).add(queue)
        try:
            yield queue
        finally:
            queues = self._queues.get(job_id)
            if queues is not None:
                queues.discard(queue)
                if not queues:
                    del self._queues[job_id]
