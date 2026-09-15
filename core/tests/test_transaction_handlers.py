"""TransactionSkill split: five domain handlers behind the thin facade.

Locks the facade contract (14 capability keys, fail-closed dispatch)
and the new structure (one handler class per domain, constructed with
only the dependencies its domain needs).
"""

from unittest.mock import MagicMock

import pytest
from aura_hive.config.crypto import CryptoSettings
from aura_hive.hive.proteins.transaction.engine import (
    PriceConverter,
    SecretEncryption,
)
from aura_hive.hive.proteins.transaction.handlers import (
    EVMHandlers,
    PaymentsHandlers,
    PricingHandlers,
    RWAHandlers,
    SecretsHandlers,
)
from aura_hive.hive.proteins.transaction.skill import TransactionSkill
from solders.keypair import Keypair

EXPECTED_CAPABILITIES = {
    "verify_payment",
    "verify_settlement",
    "generate_payment_request",
    "calculate_tax_and_margin",
    "encrypt_secret",
    "decrypt_secret",
    "get_address",
    "convert_price",
    "get_network_name",
    "transfer",
    "sign_trade_intent",
    "submit_to_router",
    "execute_rwa_collateral",
    "mint_rwa_vault",
}

EXPECTED_BY_DOMAIN = {
    PaymentsHandlers: {
        "verify_payment",
        "verify_settlement",
        "generate_payment_request",
        "get_address",
        "get_network_name",
    },
    SecretsHandlers: {"encrypt_secret", "decrypt_secret"},
    PricingHandlers: {"calculate_tax_and_margin", "convert_price"},
    EVMHandlers: {"transfer", "sign_trade_intent", "submit_to_router"},
    RWAHandlers: {"execute_rwa_collateral", "mint_rwa_vault"},
}


def _settings() -> CryptoSettings:
    keypair = Keypair()
    return CryptoSettings(
        enabled=True, solana_private_key=str(keypair), secret_encryption_key="k" * 44
    )


def _provider_bundle():
    return {
        "provider": MagicMock(),
        "solana_provider": MagicMock(),
        "evm_provider": MagicMock(),
        "encryption": MagicMock(),
        "converter": PriceConverter(),
    }


def test_handler_domains_cover_every_capability_exactly_once():
    covered: set[str] = set()
    for cls, keys in EXPECTED_BY_DOMAIN.items():
        assert set(cls.capabilities) == keys, cls.__name__
        assert not (covered & keys), f"overlap in {cls.__name__}"
        covered |= keys
    assert covered == EXPECTED_CAPABILITIES


def test_facade_capability_map_is_stable():
    assert set(TransactionSkill().get_capabilities()) == EXPECTED_CAPABILITIES


@pytest.mark.asyncio
async def test_facade_routes_each_domain_through_handlers():
    skill = TransactionSkill()
    skill.bind(_settings(), _provider_bundle())
    # Pricing is real logic (no mock): proves the facade reaches the handler.
    obs = await skill.execute("calculate_tax_and_margin", {"price": 100.0})
    assert obs.success is True
    assert obs.metadata.to_dict()["margin"] == 10.0
    # Secrets handler is wired (mock encryption round-trips through it).
    obs = await skill.execute("encrypt_secret", {"secret": "s"})
    assert obs.success is True
    # Unknown intent still fails closed.
    obs = await skill.execute("nope", {})
    assert obs.success is False


@pytest.mark.asyncio
async def test_facade_still_fails_closed_when_uninitialized():
    skill = TransactionSkill()
    obs = await skill.execute("get_address", {})
    assert obs.success is False
    assert "not_initialized" in obs.error


def test_handlers_take_only_their_own_dependencies():
    bundle = _provider_bundle()
    settings = _settings()
    # Each handler constructs with a narrow slice — no whole-skill backref.
    PaymentsHandlers(provider=bundle["provider"])
    SecretsHandlers(
        encryption=SecretEncryption("3fRk6F9g9V9f9V9f9V9f9V9f9V9f9V9f9V9f9V9f9V8=")
    )
    PricingHandlers(converter=bundle["converter"], settings=settings)
    EVMHandlers(evm_provider=bundle["evm_provider"])
    RWAHandlers(solana_provider=bundle["solana_provider"], settings=settings)
