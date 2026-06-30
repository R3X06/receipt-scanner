"""Provider ports + a small swappable registry (ports & adapters).

Two external dependencies sit behind ports: FX rate conversion and receipt OCR.
The default adapters delegate verbatim to the existing fx/ocr modules, so
production behaviour is unchanged — this module only introduces a seam.

Why a module-level registry instead of FastAPI Depends: the FX dependency is used
inside ledger.post_entry, a plain function below the request boundary that Depends
cannot reach. A registry resolves uniformly for both the engine and the endpoints,
and gives tests one swap point: set_fx(fake) ... reset_fx().

Import DAG: providers -> fx, ocr (for the defaults). ledger/main -> providers.
providers never imports ledger, so there is no cycle.
"""
from typing import Protocol

import fx as _fx
import ocr as _ocr


# ---------------------------------------------------------------- ports
class FXProvider(Protocol):
    def convert_to_base(self, *, amount, currency, base_currency,
                        receipt_date_str) -> dict: ...


class OCRProvider(Protocol):
    def extract_text(self, image_bytes: bytes) -> str: ...


# ---------------------------------------------------------------- default adapters
class DefaultFXProvider:
    """Frankfurter-backed conversion (never raises). Delegates to fx.convert_to_base."""
    def convert_to_base(self, *, amount, currency, base_currency, receipt_date_str):
        return _fx.convert_to_base(amount=amount, currency=currency,
                                   base_currency=base_currency,
                                   receipt_date_str=receipt_date_str)


class DefaultOCRProvider:
    """Google Vision-backed OCR. Delegates to ocr.extract_text_from_image."""
    def extract_text(self, image_bytes: bytes) -> str:
        return _ocr.extract_text_from_image(image_bytes)


# ---------------------------------------------------------------- registry
_fx_provider: FXProvider = DefaultFXProvider()
_ocr_provider: OCRProvider = DefaultOCRProvider()


def get_fx() -> FXProvider:
    return _fx_provider


def set_fx(provider: FXProvider) -> None:
    global _fx_provider
    _fx_provider = provider


def reset_fx() -> None:
    global _fx_provider
    _fx_provider = DefaultFXProvider()


def get_ocr() -> OCRProvider:
    return _ocr_provider


def set_ocr(provider: OCRProvider) -> None:
    global _ocr_provider
    _ocr_provider = provider


def reset_ocr() -> None:
    global _ocr_provider
    _ocr_provider = DefaultOCRProvider()