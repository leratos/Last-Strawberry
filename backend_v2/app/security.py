import re

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)([^\s,;]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(bearer\s+)([^\s,;]+)"), r"\1[REDACTED]"),
    (
        re.compile(r'(?i)("?(?:api[_-]?key|token|secret|password)"?\s*[:=]\s*"?)([^"\s,;]+)("?)'),
        r"\1[REDACTED]\3",
    ),
]


def sanitize_for_log(value: object, *, max_length: int = 120) -> str:
    text = str(value)
    cleaned = re.sub(r"[\r\n\t]+", " ", text).strip()
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[:max_length]}..."


def redact_sensitive_text(text: object, *, max_length: int = 500) -> str:
    cleaned = sanitize_for_log(text, max_length=max_length)
    redacted = cleaned
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
