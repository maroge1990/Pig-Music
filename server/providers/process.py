"""Bounded, cancellable child processes for decoding and future extractors."""

import os
import signal
import subprocess
import tempfile
import time


def run_checked(argv, check, timeout, max_output_bytes=1_000_000):
    """Run argv without a shell; stop the entire child group on interruption.

    Temporary streams avoid pipe deadlocks and unbounded in-memory capture.
    Their combined size is checked while the process runs and before return.
    """
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=os.name == "posix",
        )
        deadline = time.monotonic() + timeout

        try:
            while True:
                check()
                if (
                    os.fstat(stdout.fileno()).st_size
                    + os.fstat(stderr.fileno()).st_size
                    > max_output_bytes
                ):
                    raise ValueError("Audio process exceeded its output limit")
                if process.poll() is not None:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Audio process exceeded its time limit")
                time.sleep(0.05)
        finally:
            # A parent may exit while its descendants still hold output files.
            # The isolated group must be cleaned up even after parent exit.
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    # macOS sandbox can report EPERM for an already vanished
                    # group. Never suppress refusal to stop a live parent.
                    if process.poll() is None:
                        process.kill()
                        process.wait()
                        raise
            elif process.poll() is None:
                process.kill()
            process.wait()
        stdout.seek(0)
        stderr.seek(0)
        return subprocess.CompletedProcess(
            argv, process.returncode, stdout.read(), stderr.read()
        )
