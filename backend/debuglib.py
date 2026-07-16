"""Lightweight self-instrumentation for the ledger engine.

Two independent switches, both OFF by default so production pays nothing:

  KALLA_TRACE=1            -> @traced logs every wrapped call (arg summary,
                             result summary, elapsed ms; full traceback on error)
  KALLA_INVARIANTS=strict  -> a broken invariant RAISES; otherwise it logs ERROR

The invariants encode the engine's contract - money is conserved, nothing
exceeds its cap - which is the executable form of KALLA's thesis: balances are
derived, and the derivation is *checked*, not trusted.
"""
import functools
import logging
import os
import time
import traceback

log = logging.getLogger("kalla.ledger")

# Money math tolerance. The engine rounds to cents and treats <0.005 as zero,
# so comparisons allow one cent of slack to avoid false positives on float dust.
CENT = 0.01


def _tracing() -> bool:
    return os.getenv("KALLA_TRACE", "").lower() in ("1", "true", "yes", "on")


def _strict() -> bool:
    return os.getenv("KALLA_INVARIANTS", "").lower() == "strict"


# When tracing is on, make sure the log actually surfaces even if the app's root
# logger sits at INFO. Attach one DEBUG console handler to our logger, once.
if _tracing() and not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.DEBUG)
    log.propagate = False


def _summarize(v):
    """Compact, safe repr for a log line: scalars shown (truncated), collections
    sized, everything else shown by type only - never dumps a db session, a user
    row, or a giant list into the logs."""
    if isinstance(v, (int, float, bool, str, type(None))):
        s = repr(v)
        return s if len(s) <= 60 else s[:57] + "..."
    if isinstance(v, (list, tuple, set, dict)):
        return f"<{type(v).__name__} len={len(v)}>"
    return f"<{type(v).__name__}>"


def traced(fn):
    """Log entry (arg summary), exit (result summary + ms) and any exception
    (with traceback) for `fn` - but only when KALLA_TRACE is set. When off,
    returns the function untouched, so there is zero wrapper overhead in prod."""
    if not _tracing():
        return fn

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        argstr = ", ".join(
            [_summarize(a) for a in args]
            + [f"{k}={_summarize(v)}" for k, v in kwargs.items()]
        )
        log.debug("-> %s(%s)", fn.__name__, argstr)
        t0 = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            dt = (time.perf_counter() - t0) * 1000
            log.error("!! %s raised %s after %.1fms\n%s",
                      fn.__name__, type(exc).__name__, dt, traceback.format_exc())
            raise
        dt = (time.perf_counter() - t0) * 1000
        log.debug("<- %s => %s [%.1fms]", fn.__name__, _summarize(result), dt)
        return result

    return wrapper


def _violation(name, msg, context=""):
    """Report one broken invariant. Always logs an ERROR; raises only under
    strict mode, so production degrades loudly-in-logs rather than 500-ing."""
    detail = f"INVARIANT [{name}] violated: {msg}"
    if context:
        detail += f" | {context}"
    if _strict():
        raise AssertionError(detail)
    log.error(detail)


def verify_allocation(savings, goals, result, *, tol=CENT):
    """Check every contract one goal_allocations run must satisfy, then return
    `result` unchanged so it can wrap a return statement inline.

    Contracts:
      1. conservation   - sum(allocations) + unallocated == max(savings, 0)
      2. non-negativity - no goal (and not unallocated) goes below zero
      3. no overshoot   - no goal with a numeric target exceeds it

    `goals` are the normalized goal dicts (each needs `id` and `target_amount`;
    a None target means open-ended / uncapped).
    """
    allocs = result.get("allocations", {})
    unalloc = result.get("unallocated", 0.0)

    # Compare money at cent resolution: round the *difference* before testing,
    # so float representation dust at the boundary (e.g. 0.21 - 0.22 giving
    # -0.01000000002) can't false-trip. Real leaks are >= 2 cents and still caught.
    def over(diff):
        return round(abs(diff), 2) > tol

    # 1. conservation. The engine rounds each goal's allocation to cents
    # independently, so the sum can legitimately drift from the true remainder by
    # up to ~half a cent per goal. Conservation therefore holds to a bound that
    # scales with goal count, NOT to an exact cent. A real leak (sign error,
    # dropped allocation) is dollar-scale and still caught.
    ctol = max(tol, round(0.01 * len(allocs), 2))
    expected = max(round(savings, 2), 0.0)
    got = round(sum(allocs.values()) + unalloc, 2)
    if round(abs(got - expected), 2) > ctol:
        _violation("conservation",
                   f"allocated+unallocated={got} != savings={expected}",
                   f"delta={round(got - expected, 2)} tol={ctol}")

    # 2/3. per-goal non-negativity and cap
    targets = {g["id"]: g.get("target_amount") for g in goals}
    for gid, amt in allocs.items():
        if round(amt, 2) < -tol:
            _violation("non_negative", f"goal {gid} allocated {amt}")
        tgt = targets.get(gid)
        if tgt is not None and round(amt - tgt, 2) > tol:
            _violation("cap", f"goal {gid} allocated {amt} over target {tgt}",
                       f"overshoot={round(amt - tgt, 2)}")

    if round(unalloc, 2) < -tol:
        _violation("unallocated_sign", f"unallocated={unalloc}")

    return result