from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_WHITESPACE = re.compile(r"\s+")
_TRACKING_KEYS = {
    "from",
    "ref",
    "source",
    "spm",
    "track",
    "tracking",
}
_TRACKING_PREFIXES = ("utm_",)


def canonicalize_url(url: str) -> str:
    """Return a stable URL for identity/deduplication.

    Only obvious tracking parameters and fragments are removed. Semantic query
    parameters are preserved and sorted so the canonicalization remains
    conservative.
    """
    raw = (url or "").strip()
    if not raw:
        return raw

    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw

    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if not scheme or not hostname:
        return raw

    try:
        port = parsed.port
    except ValueError:
        return raw

    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname

    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.casefold()
        if lowered in _TRACKING_KEYS or any(lowered.startswith(prefix) for prefix in _TRACKING_PREFIXES):
            continue
        query_items.append((key, value))
    query_items.sort()

    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, urlencode(query_items, doseq=True), ""))


def normalize_identity_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    return _WHITESPACE.sub(" ", normalized).strip().casefold()


def build_content_hash(title: str, summary: str) -> str:
    """Build a provider-independent content fingerprint for duplicate detection."""
    payload = f"{normalize_identity_text(title)}\n{normalize_identity_text(summary)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
