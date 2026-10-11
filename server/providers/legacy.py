"""Run retained HTML/API parsers inside a bounded, guarded search process."""

import json
import sys
import tempfile
from pathlib import Path
from .contracts import ProviderError
from .process import run_checked


def search(source, query, context, limit=20):
    with tempfile.TemporaryDirectory(prefix=".provider-search-") as directory:
        manifest = Path(directory) / "request.json"
        manifest.write_text(
            json.dumps({"source": source, "query": query, "limit": limit})
        )
        result = run_checked(
            [sys.executable, "-m", "server.providers.legacy_worker", str(manifest)],
            lambda: context.remaining(),
            context.remaining(),
            max_output_bytes=3_000_000,
        )
        try:
            value = json.loads(result.stdout)
        except (ValueError, UnicodeError) as exc:
            raise ProviderError("invalid_response") from exc
        if result.returncode or "error" in value:
            raise ProviderError(value.get("error", "unavailable"))
        return value["candidates"]
