"""Observability gate — fail-closed FX behavior.

A cross-currency conversion failure must raise FXUnavailableError (not fabricate a
1:1 rate), and the write endpoints must surface it as a clean 503 rather than
persisting a silently-wrong base amount. Same-currency entries never call out.
"""
import pytest

import fx
import providers


def test_cross_currency_failure_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("rate service down")
    monkeypatch.setattr(fx.requests, "get", boom)
    with pytest.raises(fx.FXUnavailableError):
        fx.convert_to_base(amount=100, currency="USD",
                           base_currency="SGD", receipt_date_str="2026-06-01")


def test_same_currency_never_calls_out(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("same-currency should not hit the network")
    monkeypatch.setattr(fx.requests, "get", boom)
    res = fx.convert_to_base(amount=100, currency="SGD",
                             base_currency="SGD", receipt_date_str=None)
    assert res["amount_base"] == 100.0
    assert res["fx_rate"] == 1.0


class _RaisingFX:
    def convert_to_base(self, **kwargs):
        raise fx.FXUnavailableError("rate unavailable")


def test_expense_endpoint_returns_503_when_fx_unavailable(client):
    token = client.post("/auth/signup",
                        json={"email": "fx@b.com", "password": "demo1234"}).json()["access_token"]
    providers.set_fx(_RaisingFX())           # rate service "down" for this write
    try:
        r = client.post("/ledger/expense", json={"amount": 20, "currency": "USD"},
                        headers={"Authorization": f"Bearer {token}"})
    finally:
        providers.reset_fx()
    assert r.status_code == 503
    assert "temporarily unavailable" in r.text