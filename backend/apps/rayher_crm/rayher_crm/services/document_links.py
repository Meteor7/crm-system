"""Validation for user-maintained external scorecard references (never fetched)."""
from urllib.parse import urlsplit


def scorecard_url(value):
    if value is None or value == "":
        return ""
    if not isinstance(value, str):
        raise ValueError("Enter an absolute HTTP or HTTPS URL.")
    value = value.strip()
    if not value:
        return ""
    if len(value) > 2048 or any(ord(char) <= 32 or ord(char) == 127 for char in value) or "\\" in value:
        raise ValueError("Enter a URL without spaces, at most 2048 characters.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
        valid = parsed.scheme.lower() in {"http", "https"} and parsed.hostname and parsed.username is None and parsed.password is None
        if not valid or (port is not None and not 1 <= port <= 65535):
            raise ValueError
    except ValueError as exc:
        raise ValueError("Enter an absolute HTTP or HTTPS URL without credentials.") from exc
    return value
