"""Structured observability logging (CLAUDE.md section 18).

Every log line is a single JSON object so it can be filtered/grepped/ingested
by a real log pipeline in an enterprise setting. Any field whose name looks
like it could hold a secret is dropped before writing -- this is the logging
side of the Data Protection guardrail.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

# Precise patterns rather than bare substrings: a bare "token" or "key" would
# false-positive on legitimate, non-secret observability fields this app
# needs to log verbatim -- e.g. LLM `tokens_used`/`input_tokens`/
# `output_tokens`/`token_usage`, or a data-quality check literally named
# `duplicate_rate:record_id`... which contains no such substring anyway, but
# `tokens_used` would have been destroyed by a bare "token" match. These
# patterns still catch real secret-shaped field names.
_SENSITIVE_KEY_PATTERNS = [
    re.compile(r"api[_-]?key", re.I),
    re.compile(r"private[_-]?key", re.I),
    re.compile(r"access[_-]?token", re.I),
    re.compile(r"auth[_-]?token", re.I),
    re.compile(r"secret[_-]?token", re.I),
    re.compile(r"secret", re.I),
    re.compile(r"password", re.I),
    re.compile(r"credential", re.I),
]

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

_logger = logging.getLogger("pharma_agentic")
if not _logger.handlers:
    _logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    file_handler = logging.FileHandler(_LOG_DIR / "app.log")
    stream_handler = logging.StreamHandler()
    plain_formatter = logging.Formatter("%(message)s")
    file_handler.setFormatter(plain_formatter)
    stream_handler.setFormatter(plain_formatter)
    _logger.addHandler(file_handler)
    _logger.addHandler(stream_handler)
    _logger.propagate = False


def _is_sensitive_key(key: str) -> bool:
    return any(pattern.search(key) for pattern in _SENSITIVE_KEY_PATTERNS)


def _scrub(value):
    """Recursively redact sensitive-looking keys, including inside nested
    dicts/lists (needed now that trace events carry a nested `metadata`
    dict)."""
    if isinstance(value, dict):
        return {
            key: "***redacted***" if _is_sensitive_key(key) else _scrub(val)
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def log_event(event: str, level: str = "INFO", **fields) -> dict:
    """Write one structured log line and return the record (for the UI/tracer)."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **_scrub(fields),
    }
    payload = json.dumps(record, default=str)
    getattr(_logger, level.lower(), _logger.info)(payload)
    return record


def read_recent_logs(limit: int = 200) -> list[str]:
    log_file = _LOG_DIR / "app.log"
    if not log_file.exists():
        return []
    lines = log_file.read_text(encoding="utf-8").splitlines()
    return lines[-limit:]
