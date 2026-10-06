"""Bounded, deduplicated background image work with retry backoff."""

import asyncio
import logging
import time
from collections import OrderedDict

from .catalogue import background_metadata

log = logging.getLogger(__name__)


class Enrichment:
    def __init__(self, changed, capacity=128):
        self.queue = asyncio.Queue(maxsize=capacity)
        self.pending = set()
        self.retries = OrderedDict()
        self.changed = changed
        self.tasks = []

    def start(self):
        self.tasks = [asyncio.create_task(self.run()) for _ in range(2)]

    def submit(self, key, operation):
        if key in self.pending or self.retries.get(key, 0) > time.monotonic():
            return False
        if self.queue.full():
            return False
        self.pending.add(key)
        self.queue.put_nowait((key, operation))
        return True

    async def run(self):
        background_metadata.set(True)
        while True:
            key, operation = await self.queue.get()
            try:
                result = await operation()
                if result:
                    await asyncio.to_thread(self.changed)
                self.retries[key] = time.monotonic() + (86400 if result else 300)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Background artwork enrichment failed")
                self.retries[key] = time.monotonic() + 300
            finally:
                self.pending.discard(key)
                self.queue.task_done()
                while len(self.retries) > 4096:
                    self.retries.popitem(last=False)

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []
