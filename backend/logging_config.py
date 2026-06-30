"""Structured logging setup (stdlib, dependency-free).

setup_logging() is called once at startup. Format is env-aware, mirroring the
auth secret handling: JSON lines in production (machine-parseable; Railway
captures stdout), human-readable plain text locally. Level via LOG_LEVEL
(default INFO).

Usage:
    from logging_config import logger
    logger.error("FX conversion failed", extra={"fr": "USD", "to": "SGD"}, exc_info=True)
"""
import json
import logging
import os
import sys

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()

LOGGER_NAME = "kalla"
logger = logging.getLogger(LOGGER_NAME)

# Reserved LogRecord attributes — anything else passed via extra= is context.
_RESERVED = set(logging.makeLogRecord({}).__dict__.keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line: ts, level, logger, msg, + any extra context."""
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, val in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = val
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging() -> None:
    """Configure the root logger once. Idempotent (safe across re-imports)."""
    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    if ENVIRONMENT == "production":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
    root.addHandler(handler)