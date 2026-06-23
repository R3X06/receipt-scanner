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
import uuid
from datetime import datetime
import models
import fx


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
    conv = fx.convert_to_base(amount=amount, currency=currency,
                              base_currency=base_currency, receipt_date_str=date)
    entry = models.LedgerEntry(
        user_id=user.id, date=date or "", occurred_at=occurred_at or datetime.utcnow(),
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
    now = datetime.utcnow()
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
    ess = essential_monthly_spend(db, user) if getattr(user, "feature_essential_tagging", True) else None
    accounts = db.query(models.Account).filter(
        models.Account.user_id == user.id,
        models.Account.archived == False,  # noqa: E712
    ).order_by(models.Account.priority).all()
    return [account_view(user, a, balances, ess) for a in accounts]


def net_worth(db, user):
    return round(sum(account_balances(db, user.id).values()), 2)


# ---------------- cash-flow statement (monthly, advisory layer) ----------------

def cashflow(db, user, month=None):
    ym = month or datetime.utcnow().strftime("%Y-%m")
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
    if getattr(user, "feature_proportional_allocation", True):
        return "proportional"
    if getattr(user, "feature_priority_waterfall", True):
        return "waterfall"
    return "even"


def goal_allocations(savings_balance, goals, strategy="even"):
    """Derive each goal's current claim on the savings balance.
    goals: list of dicts {id, funding_type, forced_amount, target_amount, deadline, priority}.
    Forced goals reserve forced_amount off the top (senior, priority asc = filled first,
    cut last). Algorithmic goals share the remainder via `strategy`. When savings can't
    cover all forced reservations, forced goals are filled senior-first and the
    lowest-priority forced goals are cut first."""
    savings_balance = round(max(savings_balance, 0.0), 2)
    forced = [g for g in goals if g.get("funding_type") == "forced"]
    algo = [g for g in goals if g.get("funding_type") != "forced"]
    alloc = {g["id"]: 0.0 for g in goals}

    total_forced = round(sum(max(g.get("forced_amount") or 0.0, 0.0) for g in forced), 2)

    if savings_balance >= total_forced:
        for g in forced:
            alloc[g["id"]] = round(max(g.get("forced_amount") or 0.0, 0.0), 2)
        remainder = round(savings_balance - total_forced, 2)
        if algo and remainder > 0:
            for gid, amt in allocate(remainder, strategy, algo):
                alloc[gid] = round(alloc.get(gid, 0.0) + amt, 2)
        unallocated = round(savings_balance - round(sum(alloc.values()), 2), 2)
    else:
        left = savings_balance
        for g in sorted(forced, key=lambda g: g.get("priority", 0)):
            want = round(max(g.get("forced_amount") or 0.0, 0.0), 2)
            take = round(min(left, want), 2)
            alloc[g["id"]] = take
            left = round(left - take, 2)
        unallocated = 0.0

    return {"allocations": {k: round(v, 2) for k, v in alloc.items()},
            "unallocated": round(max(unallocated, 0.0), 2)}


def goals_view(db, user, strategy=None):
    """Savings balance + each goal's derived allocation (no money is stored on goals)."""
    sav = savings_account(db, user.id)
    sav_bal = round(account_balances(db, user.id).get(sav.id, 0.0), 2) if sav else 0.0
    goals = db.query(models.Goal).filter(
        models.Goal.user_id == user.id,
        models.Goal.archived == False,  # noqa: E712
    ).order_by(models.Goal.priority).all()
    gdicts = [{
        "id": g.id, "funding_type": g.funding_type or "algorithmic",
        "forced_amount": g.forced_amount, "target_amount": g.target_amount,
        "deadline": g.deadline, "priority": g.priority or 0,
    } for g in goals]
    strat = strategy or _algo_strategy(user)
    res = goal_allocations(sav_bal, gdicts, strat)
    alloc = res["allocations"]
    out = []
    for g in goals:
        a = round(alloc.get(g.id, 0.0), 2)
        item = {
            "id": g.id, "name": g.name, "funding_type": g.funding_type or "algorithmic",
            "forced_amount": g.forced_amount, "target_amount": g.target_amount,
            "deadline": g.deadline, "priority": g.priority or 0,
            "is_emergency": bool(g.is_emergency), "allocated": a,
            "currency": user.primary_currency or "SGD",
        }
        if g.target_amount and g.target_amount > 0:
            item["progress"] = round(min(a / g.target_amount, 1.0), 4)
            item["remaining"] = round(max(g.target_amount - a, 0.0), 2)
        out.append(item)
    return {"savings_balance": sav_bal, "unallocated": res["unallocated"],
            "strategy": strat, "goals": out}


# ---------------- allocation engine (shared by goal_allocations) ----------------

def _even(amount, ids):
    if not ids:
        return []
    each = round(amount / len(ids), 2)
    splits = [(i, each) for i in ids]
    _fix_rounding(splits, amount)
    return splits


def _fix_rounding(splits, total):
    if not splits:
        return
    diff = round(total - sum(a for _, a in splits), 2)
    if abs(diff) >= 0.01:
        gid, amt = splits[0]
        splits[0] = (gid, round(amt + diff, 2))


def allocate(amount, strategy, goals):
    """goals: list of dicts (id, balance, target_amount, deadline, priority).
    Returns [(goal_id, amount), ...]. 'manual' is handled by the caller."""
    amount = round(amount, 2)
    if amount <= 0 or not goals:
        return []

    if strategy == "waterfall":
        splits, left = [], amount
        for g in sorted(goals, key=lambda g: g.get("priority", 0)):
            if left <= 0:
                break
            target = g.get("target_amount")
            if target:
                room = max(target - g.get("balance", 0.0), 0.0)
                take = min(left, room)
            else:
                take = left
            if take > 0:
                splits.append((g["id"], round(take, 2)))
                left = round(left - take, 2)
        if left > 0.009:
            if splits:
                gid, amt = splits[-1]
                splits[-1] = (gid, round(amt + left, 2))
            else:
                splits.append((goals[0]["id"], amount))
        return splits

    if strategy == "proportional":
        weights = []
        for g in goals:
            months = _months_until(g.get("deadline"))
            target = g.get("target_amount")
            remaining = max((target or 0) - g.get("balance", 0.0), 0.0)
            weights.append((g["id"], (remaining / months) if (months and months > 0 and remaining > 0) else 0.0))
        total = sum(w for _, w in weights)
        if total <= 0:
            return _even(amount, [g["id"] for g in goals])
        splits = [(gid, round(amount * w / total, 2)) for gid, w in weights if w > 0]
        _fix_rounding(splits, amount)
        return splits

    return _even(amount, [g["id"] for g in goals])