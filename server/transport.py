"""Private HTTPS configuration; forwarded headers are trusted only by Uvicorn."""

import os
from urllib.parse import urlsplit


def public_origin():
    value = os.environ.get("PIG_MUSIC_PUBLIC_ORIGIN", "").rstrip("/")
    if not value:
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("PIG_MUSIC_PUBLIC_ORIGIN must be a bare HTTPS origin")
    return value


def proxy_trust():
    value = os.environ.get("PIG_MUSIC_TRUSTED_PROXIES", "127.0.0.1").strip()
    if not value or "*" in value:
        raise ValueError("Configure only the specific private proxy addresses")
    # No DNS lookups and no broad CIDR trust: the private proxy has a known address.
    from ipaddress import ip_address

    for entry in value.split(","):
        ip_address(entry.strip())
    return value
