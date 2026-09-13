"""Price conversion: USD to crypto at fixed rates, without silent answers.

`PriceConverter.FIXED_RATES` pins SOL at $100 and USDC at $1. Money math
runs through Decimal, so 150 USD is exactly 1.5 SOL — never 1.4999999.
An unsupported currency raises instead of returning a number nobody
priced.
"""

import pytest
from aura_hive.hive.proteins.transaction.engine import PriceConverter


@pytest.mark.parametrize(
    ("usd", "currency", "expected"),
    [
        pytest.param(150.0, "SOL", 1.5, id="usd-to-sol"),
        pytest.param(150.0, "USDC", 150.0, id="usd-to-usdc-peg"),
        pytest.param(0.0, "SOL", 0.0, id="zero"),
        pytest.param(0.01, "SOL", 0.0001, id="fractional"),
        pytest.param(1_000_000.0, "SOL", 10_000.0, id="large"),
        pytest.param(99.99, "USDC", 99.99, id="cents-stablecoin"),
    ],
)
def test_usd_to_crypto_conversions(usd: float, currency: str, expected: float) -> None:
    assert PriceConverter().convert_usd_to_crypto(usd, currency) == pytest.approx(
        expected
    )


def test_unsupported_currency_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported currency"):
        PriceConverter().convert_usd_to_crypto(100.0, "BTC")


def test_tax_and_margin_applies_the_homeostasis_rate() -> None:
    result = PriceConverter().calculate_tax_and_margin(100.0)

    assert result["margin"] == pytest.approx(10.0)
    assert result["tax"] == pytest.approx(0.0)
    assert result["total"] == pytest.approx(110.0)
