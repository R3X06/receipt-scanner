"""Ledger engine. Balances and reports are derived from the immutable
ledger_entries log; writes go through post_entry / the allocation engine.
NULL on an account side means 'the World' (income if `from` is NULL, an
expense if `to` is NULL).

Two flags refine derivation:
  * wallet_linked (expenses) — when false the expense leaves the wallet AND
    surplus entirely, but stays in expense analysis ("paid from untracked money").
  * inferred (income) — non-real income (e.g. a declared opening balance); it
    seeds the wallet but is excluded from the income x expense (advisory) layer.

Savings is a first-class account (a second wallet). Goals are NOT accounts —
they are derived claims over the savings balance (see goal_allocations)."""
import math
from datetime import datetime
from clock import utcnow
import models
import fx
import providers
import debuglib


def entry_base(e):
    return e.amount_base if e.amount_base is not None else (e.amount or 0.0)


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


# ---------------- writes ----------------

def post_entry(db, user, *, amount, currency=None, from_account_id, to_account_id,
               date=None, occurred_at=None, category=None, counterparty=None, note=None,
               raw_ocr_text="", parsed_ok=None, allocation_strategy=None, batch_id=None,
               wallet_linked=True, inferred=False):
    base_currency = user.primary_currency or fx.DEFAULT_BASE_CURRENCY
    currency = currency or base_currency
    conv = providers.get_fx().convert_to_base(amount=amount, currency=currency,
                              base_currency=base_currency, receipt_date_str=date)
    entry = models.LedgerEntry(
        user_id=user.id, date=date or "", occurred_at=occurred_at or utcnow(),
        amount=amount, currency=currency,
        amount_base=conv["amount_base"], base_currency=conv["base_currency"],
        fx_rate=conv["fx_rate"], fx_date=conv["fx_date"],
        from_account_id=from_account_id, to_account_id=to_account_id,
        wallet_linked=wallet_linked, inferred=inferred,
        category=category, counterparty=counterparty, note=note,
        raw_ocr_text=raw_ocr_text or "", parsed_ok=parsed_ok,
        allocation_strategy=allocation_strategy, batch_id=batch_id,
    )
    db.add(entry)
    return entry


# ---------------- balances (derived) ----------------

def account_balances(db, user_id):
    """{account_id: balance_in_base} across all of the user's accounts.
    An unlinked expense leaves every account balance untouched (expense-only)."""
    entries = db.query(models.LedgerEntry).filter(models.LedgerEntry.user_id == user_id).all()
    bal = {}
    for e in entries:
        if e.to_account_id is None and not getattr(e, "wallet_linked", True):
            continue  # unlinked expense: no effect on the wallet
        v = entry_base(e)
        if e.to_account_id:
            bal[e.to_account_id] = bal.get(e.to_account_id, 0.0) + v
        if e.from_account_id:
            bal[e.from_account_id] = bal.get(e.from_account_id, 0.0) - v
    return bal


def spending_account(db, user_id):
    return db.query(models.Account).filter(
        models.Account.user_id == user_id,
        models.Account.type == "spending",
    ).first()


def savings_account(db, user_id):
    return db.query(models.Account).filter(
        models.Account.user_id == user_id,
        models.Account.type == "savings",
    ).first()


def _months_until(deadline_iso):
    if not deadline_iso:
        return None
    try:
        d = datetime.strptime(deadline_iso[:10], "%Y-%m-%d")
    except ValueError:
        return None
    now = utcnow()
    return max((d.year - now.year) * 12 + (d.month - now.month), 0)


def essential_monthly_spend(db, user):
    """Average monthly spend on 'essential'-tagged categories (the emergency-fund denominator).
    Counts ALL expenses, linked or not — expense analysis is always complete."""
    kinds = {c.name: c.kind for c in db.query(models.Category).filter(
        models.Category.user_id == user.id).all()}
    rows = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.user_id == user.id,
        models.LedgerEntry.to_account_id.is_(None),   # expenses
    ).all()
    by_month = {}
    for e in rows:
        if kinds.get(e.category) != "essential":
            continue
        d = e.fx_date or e.date or ""
        if len(d) >= 7:
            by_month[d[:7]] = by_month.get(d[:7], 0.0) + entry_base(e)
    return (sum(by_month.values()) / len(by_month)) if by_month else 0.0


def account_view(user, account, balances, essential_spend=None):
    bal = round(balances.get(account.id, 0.0), 2)
    data = {
        "id": account.id, "type": account.type, "name": account.name,
        "balance": bal, "currency": user.primary_currency or "SGD",
        "is_emergency": bool(account.is_emergency), "priority": account.priority or 0,
        "target_amount": account.target_amount, "deadline": account.deadline,
        "archived": bool(account.archived),
    }
    if account.type == "goal" and account.target_amount:
        target = account.target_amount
        data["progress"] = round(min(bal / target, 1.0), 4) if target > 0 else None
        data["remaining"] = round(max(target - bal, 0.0), 2)
        months = _months_until(account.deadline)
        if months is not None and getattr(user, "feature_pace_tracking", True):
            data["months_left"] = months
            data["required_per_month"] = round(max(target - bal, 0.0) / months, 2) if months > 0 else round(max(target - bal, 0.0), 2)
    if account.is_emergency and essential_spend and essential_spend > 0:
        data["covers_months"] = round(bal / essential_spend, 1)
        data["essential_monthly"] = round(essential_spend, 2)
    return data


def list_accounts(db, user):
    balances = account_balances(db, user.id)
    ess = essential_monthly_spend(db, user)
    accounts = db.query(models.Account).filter(
        models.Account.user_id == user.id,
        models.Account.archived == False,  # noqa: E712
    ).order_by(models.Account.priority).all()
    return [account_view(user, a, balances, ess) for a in accounts]


def net_worth(db, user):
    return round(sum(account_balances(db, user.id).values()), 2)


# ---------------- cash-flow statement (monthly, advisory layer) ----------------

def cashflow(db, user, month=None):
    ym = month or utcnow().strftime("%Y-%m")
    entries = db.query(models.LedgerEntry).filter(models.LedgerEntry.user_id == user.id).all()
    spend = spending_account(db, user.id)
    spend_id = spend.id if spend else None

    income = spending = to_savings = from_savings = external_in = 0.0
    for e in entries:
        d = (e.fx_date or e.date or "")
        if not d.startswith(ym):
            continue
        v = entry_base(e)
        frm, to = e.from_account_id, e.to_account_id
        linked = getattr(e, "wallet_linked", True)
        inferred = getattr(e, "inferred", False)
        if frm is None and to == spend_id:
            if not inferred:                 # opening balance is not income
                income += v
        elif to is None:
            if linked:                       # unlinked expense -> expense-only, skip advisory
                spending += v
        elif frm == spend_id and to and to != spend_id:
            to_savings += v
        elif to == spend_id and frm and frm != spend_id:
            from_savings += v
        elif frm is None and to and to != spend_id:
            external_in += v

    surplus = income - spending
    net_to_savings = to_savings - from_savings
    leftover = surplus - net_to_savings
    rate = (surplus / income) if income > 0 else None
    return {
        "currency": user.primary_currency or "SGD", "month": ym,
        "income": round(income, 2), "spending": round(spending, 2),
        "surplus": round(surplus, 2), "to_savings_net": round(net_to_savings, 2),
        "external_to_savings": round(external_in, 2), "leftover": round(leftover, 2),
        "savings_rate": round(rate, 4) if rate is not None else None,
        "monthly_income_avg": monthly_income_avg(db, user),
    }

# --- insert into backend/ledger.py, directly after the existing cashflow() function ---

def _prior_month_keys(ym, n):
    y, m = int(ym[:4]), int(ym[5:7])
    keys = []
    for i in range(1, n + 1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        keys.append(f"{yy:04d}-{mm:02d}")
    return keys


def statement_summary(db, user, month=None):
    """Month-to-date spending vs. the trailing 3-month average, plus a
    category breakdown for the current month. Same expense convention as
    _ledger_expenses_for_ai in main.py (to_account_id is None = an outflow
    with no destination account = an expense). Additive read only — no
    schema change, no new table."""
    ym = month or utcnow().strftime("%Y-%m")
    entries = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.user_id == user.id,
        models.LedgerEntry.to_account_id.is_(None),
    ).all()

    def month_key(e):
        d = e.fx_date or e.date or ""
        return d[:7] if isinstance(d, str) and len(d) >= 7 else None

    monthly_totals = {}
    category_totals = {}
    for e in entries:
        mk = month_key(e)
        if not mk:
            continue
        v = entry_base(e)
        monthly_totals[mk] = monthly_totals.get(mk, 0.0) + v
        if mk == ym:
            cat = e.category or "Uncategorized"
            category_totals[cat] = category_totals.get(cat, 0.0) + v

    mtd = round(monthly_totals.get(ym, 0.0), 2)

    prior_keys = _prior_month_keys(ym, 3)
    prior_vals = [monthly_totals[k] for k in prior_keys if k in monthly_totals]
    trailing_avg = round(sum(prior_vals) / len(prior_vals), 2) if prior_vals else None

    delta_pct = None
    direction = "flat"
    if trailing_avg and trailing_avg > 0:
        delta_pct = round(((mtd - trailing_avg) / trailing_avg) * 100, 1)
        direction = "above" if delta_pct > 0.5 else ("below" if delta_pct < -0.5 else "flat")

    by_category = sorted(
        [{"name": k, "amount": round(v, 2)} for k, v in category_totals.items()],
        key=lambda c: c["amount"], reverse=True,
    )

    return {
        "currency": user.primary_currency or "SGD",
        "month": ym,
        "mtd_spending": mtd,
        "trailing_avg": trailing_avg,
        "delta_pct": delta_pct,
        "direction": direction,
        "by_category": by_category,
    }


# ---------------- wallet reconciliation ----------------

def wallet_reconciliation(db, user):
    """Running Spending balance ordered by occurred_at (wallet-linked entries only).
    Reports the deepest dip below zero as the shortfall, plus the wallet-linked
    expenses the user can review/unlink."""
    spend = spending_account(db, user.id)
    if not spend:
        return {"balance": 0.0, "shortfall": 0.0, "contributing": []}
    sid = spend.id
    entries = db.query(models.LedgerEntry).filter(models.LedgerEntry.user_id == user.id).all()
    touching = []
    for e in entries:
        if e.to_account_id is None and not getattr(e, "wallet_linked", True):
            continue  # unlinked expense never touches the wallet
        if e.from_account_id == sid or e.to_account_id == sid:
            touching.append(e)
    touching.sort(key=lambda e: e.occurred_at or _parse_dt(e.fx_date or e.date) or e.created_at or datetime.min)

    running = 0.0
    min_bal = 0.0
    for e in touching:
        v = entry_base(e)
        if e.to_account_id == sid:
            running += v
        if e.from_account_id == sid:
            running -= v
        if running < min_bal:
            min_bal = running

    shortfall = round(-min_bal, 2) if min_bal < 0 else 0.0
    contributing = []
    if shortfall > 0:
        for e in touching:
            if e.to_account_id is None and e.from_account_id == sid:
                contributing.append({
                    "id": e.id, "amount": round(entry_base(e), 2),
                    "currency": user.primary_currency or "SGD",
                    "category": e.category, "merchant": e.counterparty,
                    "date": e.date,
                    "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
                })
    return {"balance": round(running, 2), "shortfall": shortfall, "contributing": contributing}


# ---------------- goal allocations (derived claims over savings) ----------------

def _algo_strategy(user):
    """Which strategy splits the post-reserve remainder. Single explicit choice
    (the old waterfall/proportional feature-flag cascade is retired)."""
    s = (getattr(user, "savings_strategy", None) or "proportional").lower()
    return s if s in ("waterfall", "proportional", "even") else "proportional"


def _room_left(g, extra):
    """Remaining headroom on a goal during the remainder split.
    room is None for an open-ended (no-target) goal -> unbounded."""
    if g["room"] is None:
        return math.inf
    return g["room"] - extra[g["id"]]


def _spread(remainder, strategy, room_goals):
    """Split `remainder` across goals by `strategy`, capping each goal at its
    room (= target - reserve) and re-spreading any overflow onto goals that
    still have room. Iterates until the pool is spent or every goal is full.
    room_goals: [{id, room (None = unbounded), deadline, priority}].
    Returns (extra: {id: amount_from_remainder}, leftover_unallocated)."""
    extra = {g["id"]: 0.0 for g in room_goals}
    pool = round(max(remainder, 0.0), 2)
    guard = 0
    while pool > 0.005 and guard < 10000:
        guard += 1
        active = [g for g in room_goals if _room_left(g, extra) > 0.005]
        if not active:
            break

        if strategy == "waterfall":
            g = min(active, key=lambda x: x.get("priority", 0))
            give = min(pool, _room_left(g, extra))
            extra[g["id"]] += give
            pool = round(pool - give, 2)
            continue

        if strategy == "proportional":
            weighted = []
            for g in active:
                months = _months_until(g.get("deadline"))
                rem = _room_left(g, extra)
                rem = 0.0 if rem == math.inf else rem
                weighted.append((g, (rem / months) if (months and months > 0) else 0.0))
            total_w = sum(w for _, w in weighted)
            if total_w <= 0:                      # nothing deadline-weighted -> fall back to even
                weighted = [(g, 1.0) for g in active]
                total_w = float(len(active))
        else:                                     # even
            weighted = [(g, 1.0) for g in active]
            total_w = float(len(active))

        moved = 0.0
        for g, w in weighted:
            give = min(pool * (w / total_w), _room_left(g, extra))
            if give <= 0:
                continue
            extra[g["id"]] += give
            moved += give
        pool = round(pool - moved, 2)
        if moved <= 0.005:                        # safety: no progress -> stop
            break

    return {k: round(v, 2) for k, v in extra.items()}, round(max(pool, 0.0), 2)

@debuglib.traced
def goal_allocations(savings_balance, goals, strategy="proportional"):
    """Two passes over the savings pool:
      1. Reserves first. Sum every goal's reserve; if savings covers it, each goal
         is funded to its reserve. If not, reserves are filled senior-first by rank
         (the emergency fund is always most senior) and juniors are cut.
      2. Remainder by strategy. Whatever is left is split across goals (room =
         target - reserve), capping at target and re-spreading overflow. A goal with
         in_distribution=False sits out the remainder split — only its reserve is held.
    goals: [{id, reserve, target_amount, deadline, priority, is_emergency, in_distribution}]."""
    savings = round(max(savings_balance, 0.0), 2)
    norm = []
    for g in goals:
        target = g.get("target_amount")
        reserve = max(g.get("reserve") or 0.0, 0.0)
        if target is not None:
            reserve = min(reserve, max(target, 0.0))
        is_emerg = bool(g.get("is_emergency"))
        norm.append({"id": g["id"], "reserve": round(reserve, 2),
                     "target_amount": target, "deadline": g.get("deadline"),
                     # emergency fund is pinned most senior regardless of stored rank
                     "priority": -1 if is_emerg else (g.get("priority", 0) or 0),
                     "in_distribution": g.get("in_distribution", True) is not False})
    alloc = {g["id"]: 0.0 for g in norm}
    total_reserve = round(sum(g["reserve"] for g in norm), 2)

    # Pass 1 — reserves
    if savings < total_reserve:
        left = savings
        for g in sorted(norm, key=lambda x: x["priority"]):
            take = round(min(left, g["reserve"]), 2)
            alloc[g["id"]] = take
            left = round(left - take, 2)
        return debuglib.verify_allocation(savings, norm, {
            "allocations": {k: round(v, 2) for k, v in alloc.items()},
            "unallocated": 0.0})

    for g in norm:
        alloc[g["id"]] = g["reserve"]
    remainder = round(savings - total_reserve, 2)

    # Pass 2 — remainder (goals that opt out keep only their reserve: room = 0)
    room_goals = []
    for g in norm:
        target = g["target_amount"]
        if not g["in_distribution"]:
            room = 0.0
        elif target is None:
            room = None
        else:
            room = max(round(target - g["reserve"], 2), 0.0)
        room_goals.append({"id": g["id"], "room": room,
                           "deadline": g["deadline"], "priority": g["priority"]})
    extra, leftover = _spread(remainder, strategy, room_goals)
    for gid, v in extra.items():
        alloc[gid] = round(alloc[gid] + v, 2)

    return debuglib.verify_allocation(savings, norm, {
        "allocations": {k: round(v, 2) for k, v in alloc.items()},
        "unallocated": round(max(leftover, 0.0), 2)})


def _ensure_emergency(db, user):
    """Guarantee exactly one emergency-fund goal exists. Created opted-IN to the
    remainder split, matching new signups (the participation default is now uniform
    across every creation path). Demotes any stray duplicates."""
    emergencies = db.query(models.Goal).filter(
        models.Goal.user_id == user.id,
        models.Goal.is_emergency == True,  # noqa: E712
        models.Goal.archived == False,     # noqa: E712
    ).order_by(models.Goal.priority).all()
    if not emergencies:
        g = models.Goal(user_id=user.id, name="Emergency fund", is_emergency=True,
                         in_distribution=True, coverage_months=6, priority=0, reserve=None)
        db.add(g)
        db.commit()
        db.refresh(g)
        return g
    keep = emergencies[0]
    for extra in emergencies[1:]:            # collapse legacy multi-emergency data
        extra.is_emergency = False
    if len(emergencies) > 1:
        db.commit()
    return keep


def goals_view(db, user, strategy=None):
    """Savings balance + each goal's derived allocation (no money is stored on goals).
    The emergency fund's target is derived from essentials (coverage months × average
    essential monthly spend) rather than typed in."""
    _ensure_emergency(db, user)
    sav = savings_account(db, user.id)
    sav_bal = round(account_balances(db, user.id).get(sav.id, 0.0), 2) if sav else 0.0
    ess = essential_monthly_spend(db, user)
    goals = db.query(models.Goal).filter(
        models.Goal.user_id == user.id,
        models.Goal.archived == False,  # noqa: E712
    ).order_by(models.Goal.priority).all()

    def derived_target(g):
        if g.is_emergency:
            months = g.coverage_months or 6
            return round(months * ess, 2) if ess else 0.0
        return g.target_amount

    gdicts = [{
        "id": g.id, "reserve": g.reserve, "target_amount": derived_target(g),
        "deadline": g.deadline, "priority": g.priority or 0,
        "is_emergency": bool(g.is_emergency),
        "in_distribution": g.in_distribution is not False,
    } for g in goals]
    strat = strategy or _algo_strategy(user)
    res = goal_allocations(sav_bal, gdicts, strat)
    alloc = res["allocations"]

    out = []
    for g in goals:
        a = round(alloc.get(g.id, 0.0), 2)
        tgt = derived_target(g)
        item = {
            "id": g.id, "name": g.name, "reserve": round(g.reserve or 0.0, 2),
            "target_amount": tgt, "deadline": g.deadline,
            "priority": g.priority or 0, "is_emergency": bool(g.is_emergency),
            "in_distribution": g.in_distribution is not False,
            "allocated": a, "currency": user.primary_currency or "SGD",
        }
        if g.is_emergency:
            item["coverage_months"] = g.coverage_months or 6
            item["essential_monthly"] = round(ess, 2)
            item["covers_months"] = round(a / ess, 1) if ess > 0 else None
        if tgt and tgt > 0:
            item["progress"] = round(min(a / tgt, 1.0), 4)
            item["remaining"] = round(max(tgt - a, 0.0), 2)
            item["reserve_met"] = a + 1e-6 >= round(min(g.reserve or 0.0, tgt), 2)
            # pace: how much per month to reach the target by the deadline
            if (not g.is_emergency) and g.deadline and getattr(user, "feature_pace_tracking", True):
                months = _months_until(g.deadline)
                if months is not None:
                    item["months_left"] = months
                    item["required_per_month"] = (
                        round(item["remaining"] / months, 2) if months > 0 else item["remaining"]
                    )
        out.append(item)
    return {"savings_balance": sav_bal, "unallocated": res["unallocated"],
            "strategy": strat, "goals": out}

# ---------------- scenario simulation (hypothetical, never persisted) ----------------

def _category_monthly_avg(db, user):
    """Average monthly spend per category, across every month that category has
    activity - unlike essential_monthly_spend, this covers ALL categories
    (essential, discretionary, or untagged), so a category_pct adjustment can
    affect total spend regardless of the category's kind."""
    rows = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.user_id == user.id,
        models.LedgerEntry.to_account_id.is_(None),   # expenses
    ).all()
    by_cat_month = {}
    for e in rows:
        cat = e.category or "Uncategorized"
        d = e.fx_date or e.date or ""
        if len(d) < 7:
            continue
        key = (cat, d[:7])
        by_cat_month[key] = by_cat_month.get(key, 0.0) + entry_base(e)
    totals, months_seen = {}, {}
    for (cat, month), amt in by_cat_month.items():
        totals[cat] = totals.get(cat, 0.0) + amt
        months_seen[cat] = months_seen.get(cat, 0) + 1
    return {cat: round(totals[cat] / months_seen[cat], 2) for cat in totals}

def _total_monthly_spend(db, user):
    """Average monthly spend across ALL categories, using the same shared-month
    denominator method as essential_monthly_spend (sum per calendar month across
    categories, then divide by months with any activity) - so the unadjusted
    baseline matches real numbers shown elsewhere in the app exactly."""
    rows = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.user_id == user.id,
        models.LedgerEntry.to_account_id.is_(None),   # expenses
    ).all()
    by_month = {}
    for e in rows:
        d = e.fx_date or e.date or ""
        if len(d) >= 7:
            by_month[d[:7]] = by_month.get(d[:7], 0.0) + entry_base(e)
    return (sum(by_month.values()) / len(by_month)) if by_month else 0.0

@debuglib.traced
def simulate_scenario(db, user, *, months=12, adjustments=None, strategy=None):
    """Read-only 'what if' projection - never writes to the ledger or savings.
    Explicit assumption (also returned in the response, never silent): each
    simulated month, the full surplus (adjusted income - adjusted total spend)
    is treated as if deposited into savings, then run through the real
    goal_allocations engine. This is an optimistic ceiling, not a prediction -
    a shortfall month is clamped to 0 rather than drawing savings down.

    adjustments: list of dicts, each one of:
      {"type": "category_pct", "category_name": str, "pct": float}   # -20 = cut 20%
      {"type": "income_delta", "amount": float}
      {"type": "goal_coverage_months", "goal_id": str, "months": float}
    """
    adjustments = adjustments or []
    kinds = {c.name: c.kind for c in db.query(models.Category).filter(
        models.Category.user_id == user.id).all()}
    category_avg = _category_monthly_avg(db, user)   # used only to size category_pct deltas
    baseline_essential = essential_monthly_spend(db, user)
    baseline_total = _total_monthly_spend(db, user)
    income = monthly_income_avg(db, user)
    coverage_overrides = {}
    essential_delta = 0.0
    total_delta = 0.0

    for adj in adjustments:
        kind = adj.get("type")
        if kind == "category_pct":
            cat = adj.get("category_name")
            pct = adj.get("pct") or 0.0
            if cat in category_avg:
                delta = round(category_avg[cat] * (pct / 100.0), 2)   # negative = a cut
                total_delta += delta
                if kinds.get(cat) == "essential":
                    essential_delta += delta
        elif kind == "income_delta":
            income = round(income + (adj.get("amount") or 0.0), 2)
        elif kind == "goal_coverage_months":
            gid = adj.get("goal_id")
            if gid:
                coverage_overrides[gid] = adj.get("months")

    essential_spend = round(max(baseline_essential + essential_delta, 0.0), 2)
    total_spend = round(max(baseline_total + total_delta, 0.0), 2)
    monthly_surplus = max(round(income - total_spend, 2), 0.0)

    _ensure_emergency(db, user)
    sav = savings_account(db, user.id)
    starting_balance = round(account_balances(db, user.id).get(sav.id, 0.0), 2) if sav else 0.0
    goals = db.query(models.Goal).filter(
        models.Goal.user_id == user.id, models.Goal.archived == False,  # noqa: E712
    ).order_by(models.Goal.priority).all()
    strat = strategy or _algo_strategy(user)

    def derived_target(g):
        if g.is_emergency:
            cov = coverage_overrides.get(g.id, g.coverage_months or 6)
            return round(cov * essential_spend, 2) if essential_spend else 0.0
        return g.target_amount

    gdicts = [{
        "id": g.id, "name": g.name, "reserve": g.reserve,
        "target_amount": derived_target(g), "deadline": g.deadline,
        "priority": g.priority or 0, "is_emergency": bool(g.is_emergency),
        "in_distribution": g.in_distribution is not False,
    } for g in goals]

    goal_reached_month = {g["id"]: None for g in gdicts}
    savings_balance = starting_balance
    timeline = []
    for m in range(1, months + 1):
        savings_balance = round(savings_balance + monthly_surplus, 2)
        res = goal_allocations(savings_balance, gdicts, strat)
        alloc = res["allocations"]
        snapshot_goals = []
        for g in gdicts:
            a = round(alloc.get(g["id"], 0.0), 2)
            tgt = g["target_amount"]
            if tgt and tgt > 0 and a + 1e-6 >= tgt and goal_reached_month[g["id"]] is None:
                goal_reached_month[g["id"]] = m
            item = {"id": g["id"], "name": g["name"], "allocated": a, "target_amount": tgt}
            if tgt and tgt > 0:
                item["progress"] = round(min(a / tgt, 1.0), 4)
                item["remaining"] = round(max(tgt - a, 0.0), 2)
            snapshot_goals.append(item)
        timeline.append({
            "month": m, "savings_balance": savings_balance,
            "unallocated": res["unallocated"], "goals": snapshot_goals,
        })

    return {
        "assumptions": {
            "monthly_surplus": monthly_surplus,
            "adjusted_income": income,
            "adjusted_total_spend": total_spend,
            "adjusted_essential_spend": essential_spend,
            "note": ("Assumes 100% of monthly surplus (income minus all spend) is "
                     "deposited into savings every month - an optimistic ceiling, "
                     "not a prediction of actual behavior. Shortfall months are "
                     "clamped to 0 rather than drawing savings down."),
        },
        "strategy": strat,
        "starting_savings_balance": starting_balance,
        "timeline": timeline,
        "goal_reached_month": goal_reached_month,
    }

# ---------------- generated monthly income (never user-entered) ----------------

def monthly_income_avg(db, user):
    """Average monthly wallet income across the months that actually have real
    income (inferred opening balances excluded). A generated figure — there is
    no keyed monthly-income value any more."""
    spend = spending_account(db, user.id)
    if not spend:
        return 0.0
    rows = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.user_id == user.id,
        models.LedgerEntry.from_account_id.is_(None),   # inflow from the World
        models.LedgerEntry.to_account_id == spend.id,   # landing in the wallet
    ).all()
    by_month = {}
    for e in rows:
        if getattr(e, "inferred", False):
            continue
        d = e.fx_date or e.date or ""
        if len(d) >= 7:
            by_month[d[:7]] = by_month.get(d[:7], 0.0) + entry_base(e)
    if not by_month:
        return 0.0
    return round(sum(by_month.values()) / len(by_month), 2)