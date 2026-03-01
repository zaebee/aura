from unittest.mock import MagicMock

import pytest
from eth_account import Account
from hive.proteins.transaction.engine import (
    EVMProvider,
    PriceConverter,
    SecretEncryption,
)
from hive.proteins.transaction.skill import TransactionSkill

from config.crypto import CryptoSettings


@pytest.mark.asyncio
async def test_sign_trade_intent():
    # Setup
    priv_key = "0x" + "1" * 64
    account = Account.from_key(priv_key)

    settings = CryptoSettings(
        enabled=True,
        solana_private_key="5" * 44,  # Dummy base58
        evm_private_key=priv_key,
        risk_router_address="0x" + "2" * 40,
        evm_chain_id=84532,
        secret_encryption_key="k" * 44,
    )

    evm_provider = EVMProvider(
        private_key_hex=priv_key,
        rpc_url="https://sepolia.base.org",
        usdc_address="0x" + "3" * 40,
        chain_id=settings.evm_chain_id,
        risk_router_address=settings.risk_router_address,
    )

    skill = TransactionSkill()
    bundle = {
        "evm_provider": evm_provider,
        "encryption": SecretEncryption("3fRk6F9g9V9f9V9f9V9f9V9f9V9f9V9f9V9f9V9f9V8="),
        "converter": PriceConverter(),
        "provider": MagicMock(),  # Required by skill.py execute check
    }
    skill.bind(settings, bundle)

    intent = {
        "trade_id": "trade-123",
        "asset_identifier": "asset-456",
        "asset_domain": "VEHICLE",
        "proposed_price": 100.5,
        "currency_code": "USDC",
        "reasoning": "High ROI detected",
    }

    # Execute
    obs = await skill.execute("sign_trade_intent", {"intent": intent})

    # Assert
    assert obs.success is True
    meta = obs.metadata.to_dict()
    assert "signature" in meta
    assert meta["signed_by"] == account.address
    assert "structured_data" in meta

    # Verify EIP-712 structure
    sd = meta["structured_data"]
    assert sd["domain"]["name"] == "HackathonRiskRouter"
    assert sd["domain"]["version"] == "1"
    assert sd["domain"]["chainId"] == 84532
    assert sd["domain"]["verifyingContract"] == settings.risk_router_address
    assert sd["message"]["proposed_price"] == 100500000  # 100.5 * 1e6
    assert sd["message"]["trade_id"] == "trade-123"


@pytest.mark.asyncio
async def test_sign_trade_intent_fails_non_usdc():
    # Setup
    priv_key = "0x" + "1" * 64
    settings = CryptoSettings(
        enabled=True,
        solana_private_key="5" * 44,
        evm_private_key=priv_key,
        risk_router_address="0x" + "2" * 40,
        evm_chain_id=84532,
        secret_encryption_key="k" * 44,
    )

    evm_provider = EVMProvider(
        private_key_hex=priv_key,
        rpc_url="https://sepolia.base.org",
        usdc_address="0x" + "3" * 40,
        chain_id=settings.evm_chain_id,
        risk_router_address=settings.risk_router_address,
    )

    skill = TransactionSkill()
    bundle = {
        "evm_provider": evm_provider,
        "encryption": MagicMock(),
        "converter": MagicMock(),
        "provider": MagicMock(),
    }
    skill.bind(settings, bundle)

    intent = {
        "trade_id": "trade-123",
        "asset_identifier": "asset-456",
        "asset_domain": "VEHICLE",
        "proposed_price": 100.5,
        "currency_code": "EUR",  # Not USDC
        "reasoning": "High ROI detected",
    }

    # Execute & Assert
    obs = await skill.execute("sign_trade_intent", {"intent": intent})
    assert obs.success is False
    assert "only supports USDC" in obs.error
