"""Only vendor parsing runs here; app-owned transport enforces every request."""

import contextlib
import io
import json
import sys
from pathlib import Path

import httpx
from .contracts import Context, ProviderError
from .network import client, stream, status_error

HOSTS = {
    "freemp3cloud": ("freemp3cloud.com", "meln.top"),
    "zvu4no": ("zvu4it.org",),
    "jiosaavn": ("jiosaavn.com", "saavncdn.com"),
}


class ParserClient:
    def __init__(self, hosts, context, headers=None, **kwargs):
        self.hosts, self.context = hosts, context
        self.session = client()
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.session.close()

    def request(self, method, url, *, params=None, data=None, headers=None, **kwargs):
        request = self.session.build_request(
            method,
            url,
            params=params,
            data=data,
            headers={**self.headers, **(headers or {})},
        )
        with contextlib.closing(
            stream(
                self.session,
                method,
                str(request.url),
                self.hosts,
                self.context,
                headers=dict(request.headers),
                content=request.content,
            )
        ) as response:
            if response.status_code >= 400:
                raise status_error(response.status_code)
            body = bytearray()
            for chunk in response.iter_bytes(65536):
                self.context.remaining()
                body.extend(chunk)
                if len(body) > 2_000_000:
                    raise ProviderError("limit")
            return httpx.Response(
                response.status_code,
                headers={
                    k: v
                    for k, v in response.headers.items()
                    if k.lower() not in {"content-encoding", "content-length"}
                },
                content=bytes(body),
                request=response.request,
            )

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


class ParserHTTP:
    def __init__(self, hosts, context):
        self.hosts, self.context = hosts, context

    def Client(self, **kwargs):
        return ParserClient(self.hosts, self.context, **kwargs)

    def get(self, url, **kwargs):
        with self.Client() as session:
            return session.get(url, **kwargs)


def execute(request):
    from ..vendor import freemp3cloud, zvu4no, jiosaavn

    modules = {"freemp3cloud": freemp3cloud, "zvu4no": zvu4no, "jiosaavn": jiosaavn}
    source = request["source"]
    if source not in modules:
        raise ProviderError("invalid_response")
    module = modules[source]
    module.httpx = ParserHTTP(HOSTS[source], Context("native_standard"))
    with contextlib.redirect_stdout(io.StringIO()):
        candidates = getattr(module, "search_" + source)(
            request["query"], min(request.get("limit", 20), 20)
        )
    return {"candidates": candidates}


def main():
    try:
        value = execute(json.loads(Path(sys.argv[1]).read_text()))
    except ProviderError as exc:
        value = {"error": exc.code}
    except Exception:
        value = {"error": "unavailable"}
    print(json.dumps(value))
    return 1 if "error" in value else 0


if __name__ == "__main__":
    sys.exit(main())
