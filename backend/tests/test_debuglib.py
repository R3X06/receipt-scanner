"""Tier 1 — the self-instrumentation layer (debuglib).

Two things are under test:

  1. verify_allocation — the executable form of the engine's contract. It must
     PASS every real goal_allocations result and CATCH deliberately broken ones
     (a leak, an overshoot, a negative). This is the regression guard: if a future
     edit to the engine breaks conservation, the strict-mode fuzz turns red here.

  2. traced — must be a true no-op when KALLA_TRACE is unset (returns the bare
     function, zero prod overhead) and must preserve behavior when on.

The strongest test is test_engine_satisfies_invariant_strict: it runs the real
engine across many random shapes with KALLA_INVARIANTS=strict, so any violation
raises. Note the conservation bound scales with goal count — the engine rounds
each goal to cents independently, so the sum may drift ~half a cent per goal;
verify_allocation encodes that bound rather than a false 'exact' claim.
"""
import functools
import random

import pytest

import debuglib
import ledger


# --------------------------------------------------------------------------
# helpers (same goal-dict shape the engine expects)
# --------------------------------------------------------------------------
def goal(gid, *, reserve=0.0, target=None, deadline=None, priority=0,
         emergency=False, in_distribution=True):
    return {
        "id": gid, "reserve": reserve, "target_amount": target,
        "deadline": deadline, "priority": priority,
        "is_emergency": emergency, "in_distribution": in_distribution,
    }


def norm_targets(goals):
    """The (id, target) view verify_allocation needs for its cap check, matching
    how the engine normalizes targets (a numeric target is clamped at >= 0)."""
    return [{"id": g["id"],
             "target_amount": (None if g["target_amount"] is None
                               else max(g["target_amount"], 0.0))}
            for g in goals]


STRATEGIES = ["waterfall", "proportional", "even"]


# --------------------------------------------------------------------------
# verify_allocation — passes valid results, returns them unchanged
# --------------------------------------------------------------------------
def test_valid_result_passes_and_is_returned_unchanged(monkeypatch):
    monkeypatch.setenv("KALLA_INVARIANTS", "strict")  # any violation would raise
    goals = norm_targets([goal("a", target=100), goal("b", target=None)])
    res = {"allocations": {"a": 60.0, "b": 30.0}, "unallocated": 10.0}
    out = debuglib.verify_allocation(100.0, goals, res)
    assert out is res            # passthrough intact (safe to wrap a return)


# --------------------------------------------------------------------------
# verify_allocation — catches each broken contract under strict mode
# --------------------------------------------------------------------------
def test_conservation_leak_is_caught(monkeypatch):
    monkeypatch.setenv("KALLA_INVARIANTS", "strict")
    goals = norm_targets([goal("a", target=None)])
    leaked = {"allocations": {"a": 900.0}, "unallocated": 0.0}   # $100 vanished
    with pytest.raises(AssertionError, match="conservation"):
        debuglib.verify_allocation(1000.0, goals, leaked)


def test_cap_overshoot_is_caught(monkeypatch):
    monkeypatch.setenv("KALLA_INVARIANTS", "strict")
    goals = norm_targets([goal("a", target=100)])
    over = {"allocations": {"a": 130.0}, "unallocated": 0.0}     # a > its target
    with pytest.raises(AssertionError, match="cap"):
        debuglib.verify_allocation(130.0, goals, over)


def test_negative_allocation_is_caught(monkeypatch):
    monkeypatch.setenv("KALLA_INVARIANTS", "strict")
    goals = norm_targets([goal("a", target=100)])
    neg = {"allocations": {"a": -5.0}, "unallocated": 105.0}
    with pytest.raises(AssertionError, match="non_negative"):
        debuglib.verify_allocation(100.0, goals, neg)


# --------------------------------------------------------------------------
# verify_allocation — tolerance behavior
# --------------------------------------------------------------------------
def test_cent_rounding_drift_is_not_a_violation(monkeypatch):
    """A single-cent discrepancy is legitimate per-goal rounding, not a leak,
    and must not trip the invariant."""
    monkeypatch.setenv("KALLA_INVARIANTS", "strict")
    goals = norm_targets([goal("a", target=None), goal("b", target=None)])
    res = {"allocations": {"a": 500.0, "b": 499.99}, "unallocated": 0.0}  # off by 1c
    # does not raise
    assert debuglib.verify_allocation(1000.0, goals, res) is res


def test_default_mode_logs_but_does_not_raise(monkeypatch):
    """Without strict mode, a violation is logged (prod-safe) rather than raised."""
    monkeypatch.delenv("KALLA_INVARIANTS", raising=False)
    goals = norm_targets([goal("a", target=None)])
    leaked = {"allocations": {"a": 900.0}, "unallocated": 0.0}
    # returns normally despite the leak
    assert debuglib.verify_allocation(1000.0, goals, leaked) is leaked


# --------------------------------------------------------------------------
# traced — no-op when off, behavior-preserving when on
# --------------------------------------------------------------------------
def test_traced_is_noop_when_off(monkeypatch):
    monkeypatch.delenv("KALLA_TRACE", raising=False)

    def f(x):
        return x * 2

    assert debuglib.traced(f) is f      # bare function returned, zero overhead


def test_traced_preserves_behavior_and_name_when_on(monkeypatch):
    monkeypatch.setenv("KALLA_TRACE", "1")

    @functools.wraps(lambda: None)  # sanity: wraps machinery available
    def _noop():
        pass

    def add(a, b):
        return a + b

    wrapped = debuglib.traced(add)
    assert wrapped(2, 3) == 5            # same result
    assert wrapped.__name__ == "add"     # functools.wraps preserved identity


def test_traced_reraises_original_exception_when_on(monkeypatch):
    monkeypatch.setenv("KALLA_TRACE", "1")

    def boom():
        raise ValueError("kaboom")

    wrapped = debuglib.traced(boom)
    with pytest.raises(ValueError, match="kaboom"):
        wrapped()


# --------------------------------------------------------------------------
# ★ regression guard — the REAL engine satisfies the invariant, strictly
# --------------------------------------------------------------------------
@pytest.mark.parametrize("strategy", STRATEGIES)
@pytest.mark.parametrize("seed", range(60))
def test_engine_satisfies_invariant_strict(strategy, seed, monkeypatch):
    """Run ledger.goal_allocations over many random shapes with strict mode on,
    so ANY conservation/cap/sign violation raises and fails the test. This is the
    guard: break the engine's contract in a future edit and this goes red."""
    monkeypatch.setenv("KALLA_INVARIANTS", "strict")
    rng = random.Random(seed)
    n = rng.randint(1, 7)
    goals = []
    for i in range(n):
        target = round(rng.uniform(100, 3000), 2) if rng.random() < 0.8 else None
        reserve = round(rng.uniform(0, (target or 2000)), 2) if rng.random() < 0.7 else 0.0
        goals.append(goal(
            f"g{i}", reserve=reserve, target=target,
            deadline=rng.choice([None, "2026-09-01", "2027-06-01"]),
            priority=rng.randint(0, 5),
            emergency=(i == 0 and rng.random() < 0.5),
            in_distribution=rng.random() < 0.85,
        ))
    savings = round(rng.uniform(-100, 8000), 2)  # negatives clamp to 0
    res = ledger.goal_allocations(savings, goals, strategy)
    debuglib.verify_allocation(savings, norm_targets(goals), res)  # raises on violation