import requests
import base64
import os
import re

GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")

CURRENCY_PATTERNS = [
    (r'\bMYR\b|RM\s*\d', 'MYR'),
    (r'\bSGD\b|S\$', 'SGD'),
    (r'\bGBP\b|£', 'GBP'),
    (r'\bEUR\b|€', 'EUR'),
    (r'\bAUD\b|A\$', 'AUD'),
    (r'\bJPY\b|¥', 'JPY'),
    (r'\bINR\b|₹|\bRs\.?\s*\d', 'INR'),
    (r'\bUSD\b|US\$|\$\s*\d', 'USD'),
]

def detect_currency(text: str) -> str:
    for pattern, currency in CURRENCY_PATTERNS:
        if re.search(pattern, text):
            return currency
    return "USD"

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
        text = data["responses"][0]["fullTextAnnotation"]["text"]
        return text
    except (KeyError, IndexError):
        print("VISION RESPONSE:", data)
        return ""

def parse_receipt(text: str) -> dict:
    amount = None
    date = None
    merchant = None

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    if lines:
        merchant = lines[0]

    amount_patterns = [
        r'total[^0-9]*([\d]+\.[\d]{2})',
        r'amount[^0-9]*([\d]+\.[\d]{2})',
        r'grand[^0-9]*([\d]+\.[\d]{2})',
        r'subtotal[^0-9]*([\d]+\.[\d]{2})',
    ]
    for i, line in enumerate(lines):
        for pattern in amount_patterns:
            match = re.search(pattern, line.lower())
            if match:
                amount = float(match.group(1))
                break
        if not amount and "total" in line.lower():
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                match = re.search(r'([\d]+\.[\d]{2})', next_line)
                if match:
                    amount = float(match.group(1))
        if amount:
            break

    if not amount:
        amounts_found = []
        for line in lines:
            match = re.search(r'([\d]+\.[\d]{2})', line)
            if match:
                amounts_found.append(float(match.group(1)))
        if amounts_found:
            amount = max(amounts_found)

    date_patterns = [
        r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})',
        r'(\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2})',
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[\s]+\d{1,2}[\s,]+\d{4}',
    ]
    for line in lines:
        for pattern in date_patterns:
            match = re.search(pattern, line.lower())
            if match:
                date = match.group(0)
                break
        if date:
            break

    return {
        "merchant": merchant or "Unknown",
        "amount": amount or 0.0,
        "date": date or "",
        "currency": detect_currency(text),
        "parsed_ok": amount is not None
    }