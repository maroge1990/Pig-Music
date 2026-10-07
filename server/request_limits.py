"""Bound JSON request bodies before parsing, including chunked uploads."""

from starlette.responses import JSONResponse


class JsonBodyLimit:
    def __init__(self, app, limit=1024 * 1024):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope.get("path") in {"/api/v1/imports/apple", "/api/migration/import"}:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        content_type = headers.get(b"content-type", b"").split(b";")[0].strip().lower()
        if (
            scope["type"] != "http"
            or scope.get("method") not in {"POST", "PUT", "PATCH", "DELETE"}
            or content_type not in {b"application/json", b""}
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
                        "detail": "JSON request is larger than 1 MB",
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
