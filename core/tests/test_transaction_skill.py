from unittest.mock import MagicMock, patch

import pytest
from hive.proteins.transaction.engine import (
    PriceConverter,
    SecretEncryption,
    SolanaProvider,
)
from hive.proteins.transaction.skill import TransactionSkill
from solders.keypair import Keypair
from solders.pubkey import Pubkey

from config.crypto import CryptoSettings


@pytest.mark.asyncio
async def test_transaction_skill_execute_not_initialized():
    skill = TransactionSkill()
    obs = await skill.execute("get_address", {})
    assert obs.success is False
    assert "not_initialized" in obs.error

@pytest.mark.asyncio
async def test_transaction_skill_calculate_tax_and_margin():
    skill = TransactionSkill()
    keypair = Keypair()
    settings = CryptoSettings(enabled=True, solana_private_key=str(keypair), secret_encryption_key="k" * 44)

    # Mock provider and encryption since we don't need real ones for this test
    mock_provider = MagicMock()
    mock_encryption = MagicMock()
    converter = PriceConverter()

    skill.bind(settings, {
        "provider": mock_provider,
        "encryption": mock_encryption,
        "converter": converter
    })

    obs = await skill.execute("calculate_tax_and_margin", {"price": 100.0})
    assert obs.success is True
    assert obs.data["margin"] == 10.0
    assert obs.data["total"] == 110.0

@pytest.mark.asyncio
@patch("hive.proteins.transaction.engine.Pubkey.from_string")
async def test_transaction_skill_generate_payment_request(mock_from_string):
    # Mock Pubkey.from_string to handle the project's non-standard TOKEN_PROGRAM_ID
    # Use pre-created Pubkey objects to avoid recursion
    real_token_program = Pubkey(bytes([1] * 32))
    real_ata_program = Pubkey(bytes([2] * 32))
    dummy_pubkey = Pubkey(bytes([3] * 32))

    def side_effect(s):
        if "Tokenkeg" in s:
            return real_token_program
        if "AToken" in s:
            return real_ata_program
        return dummy_pubkey

    mock_from_string.side_effect = side_effect

    skill = TransactionSkill()
    keypair = Keypair()
    settings = CryptoSettings(enabled=True, solana_private_key=str(keypair), secret_encryption_key="k" * 44)

    # Use real objects for simple logic testing
    converter = PriceConverter()
    encryption = SecretEncryption("3fRk6F9g9V9f9V9f9V9f9V9f9V9f9V9f9V9f9V9f9V8=")
    provider = SolanaProvider(
        private_key_base58=str(keypair),
        rpc_url="https://api.devnet.solana.com",
        usdc_mint="Gh9ZwEmdLJ8DscKNTkTqPbNwLNNBjuSzaG9Vp2KGtKJr"
    )

    skill.bind(settings, {
        "provider": provider,
        "encryption": encryption,
        "converter": converter
    })

    obs = await skill.execute("generate_payment_request", {
        "amount": 1.5,
        "memo": "test-memo",
        "currency": "SOL"
    })
    assert obs.success is True
    assert "solana:" in obs.data
    assert "amount=1.5" in obs.data
    assert "memo=test-memo" in obs.data
