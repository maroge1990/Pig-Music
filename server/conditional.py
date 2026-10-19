"""Conditional JSON: a strong ETag over the final per-person body, 304 on a match."""

import hashlib
import json
from urllib.parse import unquote
from urllib.parse import unquote

from fastapi import Request, Response

# OpenAPI for routes that answer through `conditional_json`.
CONDITIONAL_RESPONSES = {
    200: {
        "headers": {
            "ETag": {
                "description": "Validator for this exact body; send it back as If-None-Match.",
                "schema": {"type": "string"},
            }
        }
    },
    304: {"description": "Not modified: the copy saved with this ETag is current."},
}


def conditional_json(request: Request, model, value) -> Response:
    """Serialise `value` like the route's response model, then honour If-None-Match.

    The hash covers the whole body after per-person projection, so two people
    only share a validator when they would receive identical bytes.
    """
    body = model.model_validate(value).model_dump(mode="json")
    payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
    etag = '"' + hashlib.sha256(payload).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    # Apple's generated client percent-encodes header values (`"` as `%22`).
    candidates = unquote(request.headers.get("if-none-match", "")).split(",")
    if any(value.strip().removeprefix("W/") in {etag, "*"} for value in candidates):
        return Response(status_code=304, headers=headers)
    return Response(payload, media_type="application/json", headers=headers)
