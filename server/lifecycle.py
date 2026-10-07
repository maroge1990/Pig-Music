"""Serialize household file mutations with membership and publication changes."""

from functools import wraps


def coordinated(method):
    @wraps(method)
    def run(self, *args, **kwargs):
        store = self.store if hasattr(self, "store") else self
        with store.lifecycle_lock:
            return method(self, *args, **kwargs)

    return run
