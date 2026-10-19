"""Versioned addresses for stored URLs written before U01-4 (all routes on /api/v1)."""

LEGACY_PREFIXES = (
    ("/api/artwork/", "/api/v1/covers/"),
    ("/api/library-artwork/", "/api/v1/library-artwork/"),
    ("/api/catalogue/artwork/", "/api/v1/catalogue/artwork/"),
)


def versioned(url):
    """The current address for an artwork URL that may predate /api/v1."""
    if not isinstance(url, str):
        return url
    for old, new in LEGACY_PREFIXES:
        if url.startswith(old):
            return new + url[len(old) :]
    return url
