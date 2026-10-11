"""Shared source orchestration used by acquisition and owner diagnostics."""

import shutil
import time

from .contracts import Context, ProviderError
from .credentials import Cookies
from .extractor import Extractor
from .health import Health
from .monochrome import Monochrome


class Runtime:
    def __init__(self, store):
        self.store = store
        self.health = Health()
        self.cookies = Cookies(store.directory)
        self.adapters = {
            source: Extractor(source) for source in ("youtube", "soundcloud")
        }
        # Invalid operator config should leave unrelated sources usable.
        try:
            self.adapters["monochrome"] = Monochrome()
        except ProviderError:
            pass

    def configured(self, source):
        if source in {"youtube", "soundcloud"}:
            import importlib.util

            return importlib.util.find_spec("yt_dlp") is not None and (
                source != "youtube" or shutil.which("node") is not None
            )
        if source == "monochrome":
            return source in self.adapters
        if source == "soulseek":
            return (self.store.directory / "slskd-connection.json").is_file()
        return True

    def search(self, source, target, context):
        if not self.configured(source):
            raise ProviderError("not_configured")
        with (
            self.health.operation(source),
            self.cookies.snapshot() if source == "youtube" else _anonymous() as cookie,
        ):
            context.cookie_path = cookie
            try:
                results = self.adapters[source].search(target, context)
            except ProviderError as exc:
                self.health.outcome(source, error=exc)
                raise
            self.health.outcome(source)
            return results

    def transfer(self, source, candidate, path, context):
        with (
            self.health.operation(source),
            self.cookies.snapshot() if source == "youtube" else _anonymous() as cookie,
        ):
            context.cookie_path = cookie
            try:
                return self.adapters[source].transfer(candidate, path, context)
            except ProviderError as exc:
                self.health.outcome(source, error=exc, transfer=True)
                raise

    def statuses(self):
        from . import REGISTRY

        settings = self.store.download_settings()
        return [
            {
                "id": source,
                "name": spec.name,
                "profiles": sorted(spec.profiles),
                "configured": self.configured(source),
                "enabled": source in settings["sources"],
                "session_configured": (
                    self.cookies.configured() if source == "youtube" else False
                ),
                **self.health.snapshot(source),
            }
            for source, spec in REGISTRY.items()
        ]

    def check(self, source):
        from . import REGISTRY

        if source not in REGISTRY:
            raise KeyError(source)
        if not self.configured(source):
            raise ProviderError("not_configured")
        with self.health.operation(source):
            try:
                if source in self.adapters:
                    with (
                        self.cookies.snapshot() if source == "youtube" else _anonymous()
                    ) as cookie:
                        self.adapters[source].check(
                            Context(
                                "native_standard",
                                cookie_path=cookie,
                                deadline=time.monotonic() + 30,
                                max_bytes=2_000_000,
                            )
                        )
                elif source == "soulseek":
                    from ..soulseek import Soulseek

                    if not Soulseek(self.store).health().get("connected"):
                        raise ProviderError()
                else:
                    # The retained parsers share guarded transport and a cancellable process.
                    from .legacy import search

                    search(
                        source,
                        "music",
                        Context("native_standard", deadline=time.monotonic() + 30),
                        1,
                    )
                self.health.outcome(source)
            except ProviderError as exc:
                self.health.outcome(source, error=exc)
                raise
            except Exception as exc:
                error = ProviderError()
                self.health.outcome(source, error=error)
                raise error from exc
        return next(value for value in self.statuses() if value["id"] == source)


def _anonymous():
    from contextlib import nullcontext

    return nullcontext(None)
