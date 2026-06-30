"""Single source of truth for the current time.

KALLA stores timestamps as *naive UTC*. The `DateTime` columns are
timezone-naive, and SQLite (plus Postgres `TIMESTAMP WITHOUT TIME ZONE`)
strip any offset on read-back anyway, so storing aware datetimes would only
invite naive-vs-aware comparison errors. This module makes that policy
explicit and routes every "now" through one function instead of the
deprecated `datetime.utcnow()`.

Migrating the whole stack to timezone-aware time later (`DateTime(timezone=True)`
columns + aware datetimes end to end) becomes a single-function change here.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a naive datetime (tzinfo stripped).

    Equivalent in value to the legacy ``datetime.utcnow()`` but built from the
    non-deprecated ``datetime.now(timezone.utc)``.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)