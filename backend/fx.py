import re
import requests
from datetime import datetime, date

from logging_config import logger

# Used only when a user has no primary_currency set.
DEFAULT_BASE_CURRENCY = "SGD"

FRANKFURTER_URL = "https://api.frankfurter.app"
REQUEST_TIMEOUT = 6  # seconds


class FXUnavailableError(Exception):
    """Raised when a cross-currency conversion cannot be performed (rate service
    down / unexpected response). The app refuses the write rather than silently
    storing the foreign amount as if it were already in the base currency."""


def parse_receipt_date(date_str: str):
    """Best-effort parse of a messy receipt date into a date object, or None."""
    if not date_str:
        return None

    text = date_str.strip()

    # ISO: YYYY-MM-DD or YYYY/MM/DD
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None

    # DD/MM/YYYY or MM/DD/YYYY (ambiguous; assume day-first, the global norm)
    m = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", text)
    if m:
        a, b, y = map(int, m.groups())
        if y < 100:
            y += 2000
        day, month = a, b
        if month > 12 and day <= 12:   # clearly day/month got swapped
            day, month = month, day
        try:
            return date(y, month, day)
        except ValueError:
            return None

    # Month-name formats: "Jan 5 2024", "5 Jan 2024"
    for fmt in ("%b %d %Y", "%d %b %Y", "%B %d %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text[:30], fmt).date()
        except ValueError:
            continue

    return None


def _clamp_date(d: date) -> date:
    today = date.today()
    return today if d > today else d


def convert_to_base(amount: float, currency: str, base_currency: str, receipt_date_str: str):
    """Convert amount/currency to base_currency at the ECB rate for the receipt
    date (falling back to the save date). Raises FXUnavailableError if a needed
    cross-currency rate cannot be obtained (same-currency never calls out)."""
    base_currency = (base_currency or DEFAULT_BASE_CURRENCY).upper()
    currency = (currency or base_currency).upper()

    parsed = parse_receipt_date(receipt_date_str)
    use_date = _clamp_date(parsed) if parsed else date.today()

    # Same currency: no conversion / no API call.
    if currency == base_currency:
        return {
            "amount_base": round(amount, 2),
            "base_currency": base_currency,
            "fx_rate": 1.0,
            "fx_date": use_date.isoformat(),
        }

    try:
        url = f"{FRANKFURTER_URL}/{use_date.isoformat()}"
        params = {"from": currency, "to": base_currency}
        res = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        data = res.json()
        rate = data["rates"][base_currency]
        return {
            "amount_base": round(amount * rate, 2),
            "base_currency": base_currency,
            "fx_rate": rate,
            # Frankfurter returns the actual date used (prior working day on weekends).
            "fx_date": data.get("date", use_date.isoformat()),
        }
    except Exception as exc:
        # Fail closed: do NOT fabricate a 1:1 rate (that would silently record the
        # foreign amount as a base-currency amount). Log loudly and refuse the write.
        logger.error(
            "fx_conversion_failed",
            exc_info=True,
            extra={"from_currency": currency, "to_currency": base_currency,
                   "date": use_date.isoformat()},
        )
        raise FXUnavailableError(
            f"Could not convert {currency}->{base_currency} for {use_date.isoformat()}"
        ) from exc