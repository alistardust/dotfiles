"""Sanitization utilities for untrusted strings."""
import re

_ANSI_ESCAPE_RE = re.compile(
    r"\x1b\[[0-9;]*[a-zA-Z]"
    r"|\x1b\][^\x07]*\x07"
    r"|\x1b[^[]\S"
)

_TOKEN_PATTERNS = re.compile(
    r"(access_token|refresh_token|bearer|authorization)"
    r"\s*[:=]\s*\S+",
    re.IGNORECASE,
)


def sanitize_for_terminal(s: str) -> str:
    """Strip ANSI escape sequences and non-printable control chars."""
    s = _ANSI_ESCAPE_RE.sub("", s)
    return "".join(c for c in s if c.isprintable() or c in "\n\t")


def sanitize_exception(e: Exception) -> str:
    """Redact potential tokens from exception messages."""
    msg = str(e)
    # Bearer pattern first (catches "Authorization: Bearer <token>" as a whole)
    msg = re.sub(
        r"Bearer\s+[A-Za-z0-9._~+/=-]+",
        "Bearer <REDACTED>",
        msg,
    )
    # Then individual token key=value patterns
    msg = _TOKEN_PATTERNS.sub(r"\1=<REDACTED>", msg)
    return msg


def truncate(s: str, max_len: int = 500) -> str:
    """Truncate string to max_len characters."""
    return s[:max_len] if len(s) > max_len else s
