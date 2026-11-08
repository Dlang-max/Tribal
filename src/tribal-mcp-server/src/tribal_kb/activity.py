"""Broadcast observed curator activity to independent bounded browser queues."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any


class ActivityBus:
    """Keep slow browsers from delaying other subscribers or curator tools."""

    # Set a finite per-browser event buffer.
    def __init__(self, queue_size: int = 128) -> None:
        if queue_size < 1:
            raise ValueError("queue_size must be positive")
        self.queue_size = queue_size
        self._subscribers: set[asyncio.Queue] = set()

    # Broadcast an event while dropping the oldest event for lagging browsers.
    async def publish(self, event: dict[str, Any]) -> None:
        event = {**event, "timestamp": event.get("timestamp") or datetime.now(timezone.utc).isoformat()}
        for queue in tuple(self._subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(dict(event))

    # Register and reliably remove a subscriber even when its connection closes.
    @asynccontextmanager
    async def subscribe(self):
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.queue_size)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)
