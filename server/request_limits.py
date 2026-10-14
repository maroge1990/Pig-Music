"""Bound request bodies before parsing, including chunked uploads.

Every body is bounded whatever its content type: FastAPI also parses
`application/*+json`, so checking only `application/json` left a bypass.
Import uploads stream their own larger bound instead.
"""

from starlette.responses import JSONResponse

# Routes that read the stream themselves with a 20 MB bound.
STREAMED_UPLOADS = {
    "/api/v1/imports/apple",
    "/api/v1/imports/apple/preview",
    "/api/migration/import",
}


class JsonBodyLimit:
    def __init__(self, app, limit=1024 * 1024):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope.get("path") in STREAMED_UPLOADS
            or scope.get("method") not in {"POST", "PUT", "PATCH", "DELETE"}
        ):
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > self.limit:
                return await JSONResponse(
                    {
                        "detail": "Request is larger than 1 MB",
                        "code": "request_too_large",
                    },
                    status_code=413,
                )(scope, receive, send)
            chunks.append(message.get("body", b""))
            if not message.get("more_body"):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {
                    "type": "http.request",
                    "body": b"".join(chunks),
                    "more_body": False,
                }
            return await receive()

        await self.app(scope, bounded_receive, send)
