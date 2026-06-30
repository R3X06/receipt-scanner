"""Tier 1 — the allocation engine (ledger.goal_allocations / _spread).

These are pure functions over a savings balance and a list of goal dicts: no
database, no FX, no network. They are the correctness core of KALLA, so they get
the most thorough coverage. The starred test (conservation) is the single
strongest property: money is never created or destroyed by the split.

Goal dict shape expected by goal_allocations():
    {id, reserve, target_amount, deadline, priority, is_emergency, in_distribution}
Return shape: {"allocations": {id: amount}, "unallocated": float}
"""
import random
import pytest

import ledger


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def goal(gid, *, reserve=0.0, target=None, deadline=None, priority=0,
         emergency=False, in_distribution=True):
    return {
        "id": gid, "reserve": reserve, "target_amount": target,
        "deadline": deadline, "priority": priority,
        "is_emergency": emergency, "in_distribution": in_distribution,
    }


def alloc(savings, goals, strategy="proportional"):
    res = ledger.goal_allocations(savings, goals, strategy)
    return res["allocations"], res["unallocated"]


STRATEGIES = ["waterfall", "proportional", "even"]


# --------------------------------------------------------------------------
# ★ Conservation — sum(allocations) + unallocated == clamped savings
# --------------------------------------------------------------------------
@pytest.mark.parametrize("strategy", STRATEGIES)
def test_conservation_simple(strategy):
    goals = [goal("a", reserve=200, target=500),
             goal("b", reserve=200, target=500)]
    allocs, unalloc = alloc(1000, goals, strategy)
    assert abs(sum(allocs.values()) + unalloc - 1000) < 0.02


@pytest.mark.parametrize("strategy", STRATEGIES)
@pytest.mark.parametrize("seed", range(40))
def test_conservation_randomized(strategy, seed):
    """Approximates a property-based check without the hypothesis dependency:
    across many random shapes, the split conserves the (clamped) savings pool."""
    rng = random.Random(seed)
    n = rng.randint(1, 4)
    goals = []
    for i in range(n):
        has_target = rng.random() < 0.8
        target = round(rng.uniform(100, 2000), 2) if has_target else None
        reserve = round(rng.uniform(0, (target or 1500)), 2)
        goals.append(goal(
            f"g{i}", reserve=reserve, target=target,
            deadline=rng.choice([None, "2026-09-01", "2027-01-01"]),
            priority=rng.randint(0, 5),
            emergency=(i == 0 and rng.random() < 0.5),
            in_distribution=rng.random() < 0.85,
        ))
    savings = round(rng.uniform(0, 4000), 2)
    allocs, unalloc = alloc(savings, goals, strategy)
    expected = round(max(savings, 0.0), 2)
    assert abs(sum(allocs.values()) + unalloc - expected) < 0.05
    # no goal is ever funded to a negative amount
    assert all(v >= -1e-9 for v in allocs.values())


# --------------------------------------------------------------------------
# Pass 1 — reserves
# --------------------------------------------------------------------------
def test_reserves_fully_funded_when_savings_covers_them():
    goals = [goal("a", reserve=200, target=500),
             goal("b", reserve=300, target=500)]
    allocs, _ = alloc(1000, goals, "even")
    assert allocs["a"] >= 200
    assert allocs["b"] >= 300


def test_reserves_filled_senior_first_when_short():
    # total reserve 400 > savings 300 -> senior (lower priority number) funded first
    goals = [goal("a", reserve=200, priority=1),
             goal("b", reserve=200, priority=2)]
    allocs, unalloc = alloc(300, goals, "even")
    assert allocs["a"] == 200      # senior fully funded
    assert allocs["b"] == 100      # junior gets the remainder, then cut
    assert unalloc == 0.0


def test_emergency_fund_is_most_senior_regardless_of_stored_priority():
    # emergency has a junior-looking stored priority (99) but must fund first
    goals = [goal("normal", reserve=200, priority=0),
             goal("emerg", reserve=200, priority=99, emergency=True)]
    allocs, _ = alloc(300, goals, "even")
    assert allocs["emerg"] == 200   # emergency funded before the normal goal
    assert allocs["normal"] == 100


def test_reserve_is_clamped_to_target():
    # reserve 500 but target 300 -> clamped to 300; never exceeds target
    goals = [goal("a", reserve=500, target=300)]
    allocs, unalloc = alloc(1000, goals, "even")
    assert allocs["a"] == 300       # capped at target, not 500
    assert unalloc == 700


def test_zero_and_negative_savings_allocate_nothing():
    goals = [goal("a", reserve=200, target=500),
             goal("b", reserve=100, target=300)]
    for s in (0, -50):
        allocs, unalloc = alloc(s, goals, "proportional")
        assert all(v == 0.0 for v in allocs.values())
        assert unalloc == 0.0


# --------------------------------------------------------------------------
# Pass 2 — remainder split by strategy
# --------------------------------------------------------------------------
def test_waterfall_fills_senior_goal_room_first():
    # savings 500, both rooms 400; waterfall fills A (senior) before B
    goals = [goal("a", target=400, priority=1),
             goal("b", target=400, priority=2)]
    allocs, unalloc = alloc(500, goals, "waterfall")
    assert allocs["a"] == 400       # senior filled to its room first
    assert allocs["b"] == 100       # junior gets the remainder
    assert unalloc == 0.0


def test_even_divides_remainder_equally():
    goals = [goal("a", target=400, priority=1),
             goal("b", target=400, priority=2)]
    allocs, unalloc = alloc(500, goals, "even")
    assert allocs["a"] == pytest.approx(250, abs=0.02)
    assert allocs["b"] == pytest.approx(250, abs=0.02)
    assert unalloc == 0.0


def test_proportional_falls_back_to_even_without_deadlines():
    # no deadlines -> deadline weighting is zero -> behaves like even
    goals = [goal("a", target=400), goal("b", target=400)]
    even_allocs, _ = alloc(500, goals, "even")
    prop_allocs, _ = alloc(500, goals, "proportional")
    assert prop_allocs["a"] == pytest.approx(even_allocs["a"], abs=0.02)
    assert prop_allocs["b"] == pytest.approx(even_allocs["b"], abs=0.02)


def test_proportional_favors_nearer_deadline():
    # A is due much sooner than B -> A is prioritized in the split
    goals = [goal("a", target=400, deadline="2026-08-01"),
             goal("b", target=400, deadline="2030-01-01")]
    allocs, unalloc = alloc(500, goals, "proportional")
    assert allocs["a"] > allocs["b"]
    assert allocs["a"] == pytest.approx(400, abs=0.02)   # sooner goal reaches target
    assert abs(sum(allocs.values()) + unalloc - 500) < 0.02


def test_overflow_respreads_onto_goals_with_room():
    # savings 1000, two rooms of 400 -> 800 placed, 200 cannot fit -> unallocated
    goals = [goal("a", target=400, priority=1),
             goal("b", target=400, priority=2)]
    allocs, unalloc = alloc(1000, goals, "waterfall")
    assert allocs["a"] == 400
    assert allocs["b"] == 400
    assert unalloc == 200            # nothing exceeds its target


def test_in_distribution_false_keeps_only_reserve():
    # A opts out of the remainder split -> holds reserve only; B absorbs the rest
    goals = [goal("a", reserve=100, target=500, in_distribution=False),
             goal("b", reserve=0, target=1000, in_distribution=True)]
    allocs, unalloc = alloc(1000, goals, "even")
    assert allocs["a"] == 100        # reserve only, no remainder share
    assert allocs["b"] == 900
    assert unalloc == 0.0


def test_open_ended_goal_absorbs_remainder():
    # target=None -> unbounded room -> takes the whole pool
    goals = [goal("a", target=None, in_distribution=True)]
    allocs, unalloc = alloc(1000, goals, "even")
    assert allocs["a"] == 1000
    assert unalloc == 0.0