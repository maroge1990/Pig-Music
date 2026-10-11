"""Owner-managed Netscape cookies, with atomic private files and snapshots."""

import http.cookiejar
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .contracts import ProviderError


class Cookies:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / "youtube-cookies.txt"

    def configured(self):
        try:
            info = self.path.lstat()
            return stat.S_ISREG(info.st_mode) and info.st_size > 0
        except FileNotFoundError:
            return False

    def save(self, text):
        if not isinstance(text, str) or not 0 < len(text.encode()) <= 262144:
            raise ValueError("Upload a Netscape cookie file smaller than 256 KiB")
        if not text.startswith(("# Netscape HTTP Cookie File", "# HTTP Cookie File")):
            raise ValueError("Upload cookies in Netscape format")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.directory, prefix=".youtube-cookies-", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(text.encode())
                stream.flush()
                os.fsync(stream.fileno())
            jar = http.cookiejar.MozillaCookieJar(str(temporary))
            try:
                jar.load(ignore_discard=True, ignore_expires=True)
            except (http.cookiejar.LoadError, ValueError) as exc:
                raise ValueError("Cookie file could not be read") from exc
            if not jar or any(
                cookie.domain.lstrip(".")
                not in {
                    "youtube.com",
                    "www.youtube.com",
                    "google.com",
                    "accounts.google.com",
                    "www.google.com",
                }
                for cookie in jar
            ):
                raise ValueError(
                    "Cookie file must contain only YouTube or Google cookies"
                )
            os.replace(temporary, self.path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def delete(self):
        self.path.unlink(missing_ok=True)

    @contextmanager
    def snapshot(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            yield None
            return
        except OSError as exc:
            raise ProviderError("access_required") from exc
        with os.fdopen(fd, "rb") as original:
            info = os.fstat(original.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 262144:
                raise ProviderError("access_required")
            os.fchmod(original.fileno(), 0o600)
            data = original.read(262145)
        with tempfile.TemporaryDirectory(
            prefix=".youtube-session-", dir=self.directory
        ) as directory:
            path = Path(directory) / "cookies.txt"
            path.write_bytes(data)
            path.chmod(0o600)
            yield str(path)
