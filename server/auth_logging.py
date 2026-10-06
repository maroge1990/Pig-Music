"""Redact credential fields from diagnostic records and validation failures."""

import logging
import re

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

SENSITIVE = frozenset(
    {
        "authorization",
        "cookie",
        "password",
        "current_password",
        "token",
        "code",
        "sig",
        "signature",
    }
)


def redact(value):
    if isinstance(value, dict):
        return {
            k: "[redacted]" if str(k).lower() in SENSITIVE else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(redact(v) for v in value)
    if isinstance(value, str):
        value = re.sub(r'(?i)\b(Bearer)\s+[^\s,;"\']+', r"\1 [redacted]", value)
        value = re.sub(
            r"""(?ix)(["']?(?:authorization|cookie|password|current_password|token|code|sig|signature)["']?\s*[:=]\s*)(["'][^"']*["']|[^\s,;&}]+)""",
            r"\1[redacted]",
            value,
        )
    return value


class CredentialFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact(record.msg)
        record.args = redact(record.args)
        return True


def install_validation_redaction(app):
    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        # Never echo submitted values (including nested credential models).
        errors = [
            {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        return JSONResponse({"detail": errors}, status_code=422)
