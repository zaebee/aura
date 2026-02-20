from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aura_core_gen.aura.core.v1 import Observation
from hive.proteins.blockchain_data.skill import GoldRushSkill
from hive.proteins.transaction.skill import TransactionSkill

from config.crypto import CryptoSettings


@pytest.mark.asyncio
async def test_goldrush_discovery():
    skill = GoldRushSkill()
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200, text="Operation ID: testOp\nEndpoint Path: /v1/test/path"
        )
        await skill._discover_endpoints({})
        assert skill.endpoints["testOp"] == "/test/path"


@pytest.mark.asyncio
async def test_goldrush_fetch_402_loop():
    skill = GoldRushSkill()
    skill.endpoints["testOp"] = "/test/path"

    registry = MagicMock()
    transaction = AsyncMock()
    persistence = AsyncMock()

    def get_skill(name):
        if name == "transaction":
            return transaction
        if name == "persistence":
            return persistence
        return None

    registry.get.side_effect = get_skill
    skill.inject_registry(registry)

    mock_resp_402 = MagicMock(status_code=402)
    mock_resp_402.headers = {
        "X-Payment-Instructions": "recipient=0x123;amount=0.05;network=base-sepolia"
    }

    mock_resp_200 = MagicMock(status_code=200, text='{"data": "success"}')

    # Mock metadata with to_dict method
    mock_metadata = MagicMock()
    mock_metadata.to_dict.return_value = {"transaction_hash": "0xhash"}

    transaction.execute.return_value = Observation(success=True, metadata=mock_metadata)
    persistence.execute.return_value = Observation(success=True)

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = [mock_resp_402, mock_resp_200]

        params = {"operation_id": "testOp", "path_params": {}, "query_params": {}}
        obs = await skill._fetch(params)

        assert obs.success is True
        assert obs.blockchain_discovery.transaction_hash == "0xhash"
        assert obs.blockchain_discovery.raw_json == '{"data": "success"}'

        transaction.execute.assert_called_once()
        persistence.execute.assert_called_once()


@pytest.mark.asyncio
async def test_transaction_skill_transfer_evm():
    skill = TransactionSkill()
    evm_provider = AsyncMock()
    evm_provider.transfer_usdc.return_value = "0xtxhash"

    settings = CryptoSettings(
        enabled=True,
        solana_private_key="56C4pQ...test",  # Dummy
        secret_encryption_key="VGVzdEtleTEyMzQ1Njc4OW9pdm5tMTIzNDU2Nzg5MDE=",  # 32 bytes base64
    )

    skill.bind(
        settings,
        {
            "evm_provider": evm_provider,
            "provider": MagicMock(),
            "encryption": MagicMock(),
            "converter": MagicMock(),
        },
    )

    obs = await skill.execute(
        "transfer",
        {"network": "base-sepolia", "recipient": "0xrecipient", "amount": 0.05},
    )

    assert obs.success is True
    assert obs.metadata.to_dict()["transaction_hash"] == "0xtxhash"
    evm_provider.transfer_usdc.assert_called_once_with("0xrecipient", 0.05)
