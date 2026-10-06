"""Shared latest-state SSE feed; bounded buffers, snapshot on every reconnect."""

import asyncio
import json
import logging

log = logging.getLogger(__name__)


class ChangeFeed:
    def __init__(self, queue_snapshot, health_snapshot):
        self.queue_snapshot = queue_snapshot
        self.health_snapshot = health_snapshot
        self.listeners = set()
        self.state = {}
        self.serial = 0
        self.tasks = []

    def start(self):
        self.tasks = [
            asyncio.create_task(self.poll("queue", self.queue_snapshot, 2)),
            asyncio.create_task(self.poll("health", self.health_snapshot, 15)),
        ]

    def publish(self, kind, value):
        if self.state.get(kind) == value:
            return
        self.state[kind] = value
        self.serial += 1
        message = self.message()
        for listener in self.listeners:
            if listener.full():
                listener.get_nowait()
            listener.put_nowait(message)

    def message(self):
        return f"id: {self.serial}\nevent: state\ndata: {json.dumps(self.state, separators=(',', ':'))}\n\n"

    async def poll(self, kind, collect, interval):
        while True:
            if self.listeners:
                try:
                    self.publish(kind, await asyncio.to_thread(collect))
                except Exception:
                    log.exception("Change-feed snapshot failed")
            await asyncio.sleep(interval)

    async def stream(self):
        listener = asyncio.Queue(maxsize=1)
        self.listeners.add(listener)
        try:
            self.publish("queue", await asyncio.to_thread(self.queue_snapshot))
            # A reconnect always receives a full current snapshot, even if IDs reset.
            while not listener.empty():
                listener.get_nowait()
            yield self.message()
            while True:
                try:
                    yield await asyncio.wait_for(listener.get(), timeout=15)
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            self.listeners.discard(listener)

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []
