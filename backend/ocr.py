import requests
import base64
import os
import re
from datetime import datetime

GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")

# A bare "$" is intentionally NOT mapped — it's ambiguous (USD/SGD/AUD/HKD all
# use it). Only explicit markers map. Anything showing just "$" falls through to
# detect_currency's `default`, which is the user's own base currency.
CURRENCY_PATTERNS = [
    (r'\bMYR\b|\bRM\s*\d', 'MYR'),
    (r'\bSGD\b|\bS\$', 'SGD'),
    (r'\bGBP\b|£', 'GBP'),
    (r'\bEUR\b|€', 'EUR'),
    (r'\bAUD\b|\bA\$', 'AUD'),
    (r'\bJPY\b|¥', 'JPY'),
    (r'\bINR\b|₹|\bRs\.?\s*\d', 'INR'),
    (r'\bUSD\b|\bUS\$', 'USD'),
]

def detect_currency(text: str, default: str = "USD") -> str:
    for pattern, currency in CURRENCY_PATTERNS:
        if re.search(pattern, text):
            return currency
    return default


def extract_text_from_image(image_bytes: bytes) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
    payload = {
        "requests": [{
            "image": {"content": image_b64},
            "features": [{"type": "TEXT_DETECTION"}]
        }]
    }
    res = requests.post(url, json=payload)
    data = res.json()
    try:
        return data["responses"][0]["fullTextAnnotation"]["text"]
    except (KeyError, IndexError):
        print("VISION RESPONSE:", data)
        return ""


# ---------- amount ----------
def _amount_from_lines(lines):
    low = [l.lower() for l in lines]
    # Priority: grand total > total (but NOT subtotal) > subtotal.
    # (?<!sub) stops "subtotal" from matching the "total" rule.
    priority = [
        r'grand\s*total[^0-9]*([\d]+\.[\d]{2})',
        r'(?<!sub)total[^0-9]*([\d]+\.[\d]{2})',
        r'subtotal[^0-9]*([\d]+\.[\d]{2})',
    ]
    for pat in priority:
        for line in low:
            m = re.search(pat, line)
            if m:
                return float(m.group(1))
    # keyword on its own line, number on the next line
    for kw in (r'(?<!sub)total', r'subtotal'):
        for i, line in enumerate(low):
            if re.search(kw, line) and not re.search(r'\d+\.\d{2}', line) and i + 1 < len(low):
                m = re.search(r'([\d]+\.[\d]{2})', low[i + 1])
                if m:
                    return float(m.group(1))
    # fallback: the largest money-looking number on the receipt
    found = [float(x) for l in lines for x in re.findall(r'\d+\.\d{2}', l)]
    return max(found) if found else None


# ---------- date ----------
_NUMERIC_DATE_RE = [
    r'\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}',     # 2026-06-17
    r'\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}',   # 17/06/2026 or 20/06/26
]
_NUMERIC_FORMATS = ["%d/%m/%Y", "%d/%m/%y", "%Y/%m/%d",
                    "%d-%m-%Y", "%d-%m-%y", "%Y-%m-%d"]
_MONTH = r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*'
_MONTHNAME_RE = [
    rf'{_MONTH}[\s\-]+\d{{1,2}}(?:st|nd|rd|th)?[\s\-,]+\d{{2,4}}',   # Jun-20-2026
    rf'\d{{1,2}}(?:st|nd|rd|th)?[\s\-]+{_MONTH}[\s\-,]+\d{{2,4}}',   # 20 Jun 2026
]

def _valid_numeric_date(s: str) -> bool:
    """Reject slash-numbers that aren't real dates (e.g. unit no. 63/64/65)."""
    for fmt in _NUMERIC_FORMATS:
        try:
            datetime.strptime(s, fmt)
            return True
        except ValueError:
            continue
    return False

def _date_from_lines(lines):
    for line in lines:
        for pat in _NUMERIC_DATE_RE:
            for m in re.finditer(pat, line):
                if _valid_numeric_date(m.group(0)):
                    return m.group(0)
        for pat in _MONTHNAME_RE:
            m = re.search(pat, line, re.IGNORECASE)
            if m:
                return m.group(0)
    return ""


def parse_receipt(text: str, base_currency: str = "USD") -> dict:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    amount = _amount_from_lines(lines)
    return {
        "merchant": (lines[0] if lines else "Unknown"),
        "amount": amount or 0.0,
        "date": _date_from_lines(lines),
        "currency": detect_currency(text, default=base_currency),
        "parsed_ok": amount is not None,
    }