"""Provider abstraction — the registry resolves defaults, swaps, and resets, and
the engine (post_entry) actually routes its FX conversion through the registry."""
import providers
import ledger


class _MarkerFX:
    """Minimal FXProvider stand-in for the swap/reset identity check."""
    def convert_to_base(self, **kwargs):
        return {}


def test_defaults_are_active_without_override():
    assert isinstance(providers.get_fx(), providers.DefaultFXProvider)
    assert isinstance(providers.get_ocr(), providers.DefaultOCRProvider)


def test_registry_swap_and_reset():
    marker = _MarkerFX()
    providers.set_fx(marker)
    assert providers.get_fx() is marker
    providers.reset_fx()
    assert isinstance(providers.get_fx(), providers.DefaultFXProvider)


def test_post_entry_routes_conversion_through_registry(db, user, make_account, fake_fx):
    # fake_fx installs FakeFX (USD->SGD = 1.35). If post_entry still called the
    # real fx module this would hit the network / return a different rate.
    spend = make_account(user, "spending")
    e = ledger.post_entry(db, user, amount=100, currency="USD",
                          from_account_id=None, to_account_id=spend.id)
    db.commit()
    db.refresh(e)
    assert e.fx_rate == 1.35
    assert e.amount_base == 135.00      # 100 USD x 1.35, proves the seam is live