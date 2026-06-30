"""FX fail-closed behavior (the observability gate).

Same-currency conversions never call out and never fail. A cross-currency
failure raises FXUnavailableError instead of silently fabricating a 1:1 rate,
and the write endpoint surfaces that as a 503 rather than persisting bad data.
"""
import pytest

import fx
import providers


def test_same_currency_does_not_call_out_or_raise():
    out = fx.convert_to_base(amount=100, currency="SGD", base_currency="SGD",
                             receipt_date_str="2026-06-01")
    assert out["fx_rate"] == 1.0
    assert out["amount_base"] == 100.0


def test_convert_raises_fxunavailable_on_http_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("network down")
    monkeypatch.setattr(fx.requests, "get", boom)
    with pytest.raises(fx.FXUnavailableError):
        fx.convert_to_base(amount=100, currency="USD", base_currency="SGD",
                           receipt_date_str="2026-06-01")


class _RaisingFX:
    def convert_to_base(self, **kwargs):
        raise fx.FXUnavailableError("rate down")


def test_write_endpoint_returns_503_when_fx_unavailable(client):
    # client installs FakeFX; override with a raising provider for this test
    providers.set_fx(_RaisingFX())
    try:
        token = client.post("/auth/signup",
                            json={"email": "fx@b.com", "password": "demo1234"}
                            ).json()["access_token"]
        r = client.post("/ledger/expense",
                        json={"amount": 100, "currency": "USD"},
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 503
        assert "temporarily unavailable" in r.text
    finally:
        providers.reset_fx()