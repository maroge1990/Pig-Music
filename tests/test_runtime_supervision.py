"""The optional source engine never takes the web server down with it."""

from server import runtime


class FakeProcess:
    def __init__(self, lifetime):
        self.lifetime = lifetime
        self.returncode = None

    def poll(self):
        if self.returncode is None and self.lifetime is not None:
            self.lifetime -= 1
            if self.lifetime <= 0:
                self.returncode = 1
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def test_engine_crash_restarts_with_backoff_while_server_keeps_running(
    tmp_path, monkeypatch
):
    clock = [0.0]
    engines = []
    server = FakeProcess(lifetime=400)

    def start_engine(root):
        engines.append((clock[0], FakeProcess(lifetime=3)))
        return engines[-1][1], None

    def sleep(seconds):
        clock[0] += 1

    monkeypatch.setenv("PIG_MUSIC_DATA", str(tmp_path))
    monkeypatch.setenv("PIG_MUSIC_EMBEDDED_ENGINE", "true")
    monkeypatch.setattr(runtime, "start_engine", start_engine)
    monkeypatch.setattr(runtime, "proxy_trust", lambda: "127.0.0.1")
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *a, **k: server)
    monkeypatch.setattr(runtime.time, "sleep", sleep)
    monkeypatch.setattr(runtime.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(runtime.signal, "signal", lambda *a: None)

    # The server outlives repeated engine crashes; only its own exit ends main.
    assert runtime.main() == 1
    starts = [at for at, _ in engines]
    assert len(starts) >= 4
    gaps = [later - earlier for earlier, later in zip(starts, starts[1:])]
    # Each restart waits longer than the last, up to the limit.
    assert gaps == sorted(gaps)
    assert gaps[1] > gaps[0]
