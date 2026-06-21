import os
import json
from collections import defaultdict

from openai import OpenAI

# Load .env defensively so OPENAI_API_KEY is available even if nothing else loaded it.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

MODEL = "gpt-4.1-nano"
MODEL2= "gpt-4.1-mini"

_client = None

# Same model is fine; bump to "gpt-4.1-mini" if you want richer phrasing in insights.
INSIGHTS_MODEL = MODEL2

INSIGHTS_SYSTEM = (
    "You are a financial assistant inside an expense-tracking app. From the JSON "
    "spending data, write 3-5 short, specific insights. All totals are in {base_currency}. "
    "Use the real numbers, one short sentence per insight, formatted as a plain list with "
    "'- '. Be concrete, not generic.\n\n"
    "Tailor the insights to the USER PROFILE when it's set:\n"
    "- If goals are given, make at least one insight speak to progress toward them.\n"
    "- If monthly income is given, mention their savings rate or what share of income they "
    "spent (monthly spend vs income).\n"
    "- If a monthly budget is given, note whether they're over or under it for the latest month.\n"
    "- Let occupation gently shape tone (e.g. a student vs full-time worker), never patronising.\n"
    "Keep advice practical and non-judgmental. If there's too little data, say so.\n\n"
    "USER PROFILE:\n{profile}\n\nDATA:\n{data}"
)


def generate_insights(expenses, base_currency, profile=None):
    if not expenses:
        return "Add a few expenses and I'll surface some insights about your spending."

    context = build_spending_context(expenses, base_currency)

    profile = profile or {}
    lines = []
    if profile.get("goals"):
        lines.append(f"Goals: {profile['goals']}")
    if profile.get("monthly_income"):
        lines.append(f"Monthly income: {profile['monthly_income']} {base_currency}")
    if profile.get("monthly_budget"):
        lines.append(f"Monthly budget: {profile['monthly_budget']} {base_currency}")
    if profile.get("occupation"):
        lines.append(f"Occupation: {profile['occupation']}")
    profile_block = "\n".join(lines) if lines else "None provided."

    system = INSIGHTS_SYSTEM.format(
        base_currency=base_currency,
        profile=profile_block,
        data=json.dumps(context),
    )

    resp = _get_client().chat.completions.create(
        model=INSIGHTS_MODEL,
        temperature=0.4,
        max_tokens=450,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": "Give me insights about my spending."},
        ],
    )
    return resp.choices[0].message.content.strip()

def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set — add it to backend/.env")
        _client = OpenAI(api_key=api_key)
    return _client


def _month_of(e):
    for v in (e.fx_date, e.date):
        if isinstance(v, str) and len(v) >= 7 and v[4] == "-":
            return v[:7]
    return None


def build_spending_context(expenses, base_currency):
    """Pre-compute aggregates in Python so the model reasons over accurate
    numbers (and a small context) rather than raw rows."""
    by_category = defaultdict(float)
    by_month = defaultdict(float)
    by_currency = defaultdict(float)
    total_base = 0.0

    for e in expenses:
        ab = e.amount_base if e.amount_base is not None else e.amount
        by_category[e.category or "Uncategorized"] += ab
        m = _month_of(e)
        if m:
            by_month[m] += ab
        by_currency[e.currency or "USD"] += e.amount
        total_base += ab

    recent = [
        {
            "merchant": e.merchant,
            "category": e.category,
            "amount": round(e.amount, 2),
            "currency": e.currency,
            "amount_base": round(e.amount_base if e.amount_base is not None else e.amount, 2),
            "date": e.fx_date or e.date,
        }
        for e in expenses[:50]  # expenses arrive newest-first
    ]

    return {
        "base_currency": base_currency,
        "expense_count": len(expenses),
        "total_spent_base": round(total_base, 2),
        "by_category_base": {k: round(v, 2) for k, v in by_category.items()},
        "by_month_base": {k: round(v, 2) for k, v in sorted(by_month.items())},
        "by_original_currency": {k: round(v, 2) for k, v in by_currency.items()},
        "recent_expenses": recent,
    }


SYSTEM_TEMPLATE = (
    "You are a concise financial assistant inside an expense-tracking app. "
    "Answer the user's question using ONLY the JSON data provided. "
    "All totals and '*_base' amounts are in {base_currency}; 'by_original_currency' "
    "holds totals in each original currency. Use the real numbers from the data, "
    "keep answers to 1-3 sentences, and if the data can't answer the question, say so "
    "plainly. Never invent transactions or figures.\n\nDATA:\n{data}"
)


def answer_question(question, expenses, base_currency):
    if not expenses:
        return "You don't have any expenses recorded yet, so there's nothing to analyze."

    context = build_spending_context(expenses, base_currency)
    system = SYSTEM_TEMPLATE.format(base_currency=base_currency, data=json.dumps(context))

    resp = _get_client().chat.completions.create(
        model=MODEL,
        temperature=0.2,
        max_tokens=400,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ],
    )
    return resp.choices[0].message.content.strip()

CATEGORIES = [
    "Food & Drink", "Transport", "Shopping", "Health",
    "Entertainment", "Utilities", "Other",
]

CATEGORIZE_SYSTEM = (
    "You categorize a receipt into exactly one of these categories:\n{categories}\n"
    "Reply with ONLY the category name, exactly as written above, and nothing else. "
    "If unsure, reply 'Other'."
)


def suggest_category(merchant, raw_text):
    merchant = (merchant or "").strip()
    snippet = (raw_text or "").strip()[:1500]  # cap tokens
    if not merchant and not snippet:
        return "Other"

    user = f"Merchant: {merchant or 'unknown'}\n\nReceipt text:\n{snippet}"
    try:
        resp = _get_client().chat.completions.create(
            model=MODEL,
            temperature=0,
            max_tokens=10,
            messages=[
                {"role": "system", "content": CATEGORIZE_SYSTEM.format(categories="\n".join(CATEGORIES))},
                {"role": "user", "content": user},
            ],
        )
        guess = resp.choices[0].message.content.strip()
    except Exception as exc:
        print(f"AI categorize failed: {exc}")
        return "Other"

    for c in CATEGORIES:
        if guess.lower() == c.lower():
            return c
    return "Other"

EXTRACT_MODEL = "gpt-4.1-mini"  # a step up from nano for recognising real brands

EXTRACT_SYSTEM = (
    "You extract fields from the raw OCR text of a receipt. Return ONLY a JSON "
    "object with keys 'merchant' and 'category'.\n\n"
    "'merchant' = the specific business, brand, store, or restaurant that sold the "
    "goods (the seller's trading name). Rules:\n"
    "- NEVER return the shopping mall, shopping centre, building, plaza, or location "
    "name. The mall is only WHERE the merchant sits, not the merchant.\n"
    "- For 'BRAND <Mall>' or 'BRAND @ Mall', return just the BRAND.\n"
    "- Expand a well-known brand abbreviation when you're confident "
    "(e.g. 'GV' -> 'Golden Village').\n"
    "- IGNORE banks, card networks, and payment processors (UOB, DBS, OCBC, VISA, "
    "Mastercard, NETS, GrabPay) — never the merchant.\n"
    "- If you genuinely can't identify the seller, use an empty string.\n"
    "Examples: 'GV Vivocity' -> 'Golden Village'; 'Starbucks Marina Bay Sands' -> "
    "'Starbucks'; 'Uniqlo Bugis Junction' -> 'Uniqlo'.\n\n"
    "'category' = exactly one of: {categories}. If unsure, use 'Other'.\n\n"
    "Return only the JSON object."
)


def extract_fields(raw_text):
    snippet = (raw_text or "").strip()[:2000]
    if not snippet:
        return {"merchant": "", "category": "Other"}
    try:
        resp = _get_client().chat.completions.create(
            model=EXTRACT_MODEL,
            temperature=0,
            max_tokens=80,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM.format(categories=", ".join(CATEGORIES))},
                {"role": "user", "content": snippet},
            ],
        )
        content = resp.choices[0].message.content.strip()
        content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(content)
        merchant = (data.get("merchant") or "").strip()
        category = data.get("category", "Other")
        if category not in CATEGORIES:
            category = "Other"
        return {"merchant": merchant, "category": category}
    except Exception as exc:
        print(f"AI extract failed: {exc}")
        return {"merchant": "", "category": "Other"}