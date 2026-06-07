import requests
import base64
import os
import re

GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")

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
        return ""

def parse_receipt(text: str) -> dict:
    amount = None
    date = None
    merchant = None

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    if lines:
        merchant = lines[0]

    amount_patterns = [
        r'total[:\s]+\$?([\d]+\.[\d]{2})',
        r'amount[:\s]+\$?([\d]+\.[\d]{2})',
        r'balance[:\s]+\$?([\d]+\.[\d]{2})',
        r'\$?([\d]+\.[\d]{2})',
    ]
    amounts_found = []
    for line in lines:
        for pattern in amount_patterns:
            match = re.search(pattern, line.lower())
            if match:
                amounts_found.append(float(match.group(1)))
                break
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
        "parsed_ok": amount is not None
    }