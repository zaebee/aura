"""MarketService deal lifecycle over mocked proteins.

Deals live in excited state (Redis) until payment, keyed by a unique memo.
Status reads walk NOT_FOUND → PENDING → PAID/EXPIRED, and every transition
is decided here — the tests pin the state machine, not the storage.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aura_core_gen.aura.core.google import protobuf
from aura_core_gen.aura.core.v1 import Observation
from aura_hive.hive.proteins.transaction.engine import SecretEncryption
from aura_hive.hive.services.market import MarketService


def _obs(success: bool = True, **fields: Any) -> Observation:
    return Observation(
        success=success, metadata=protobuf.Struct().from_dict(dict(fields))
    )


def _service(
    persistence_results: list | None = None,
    transaction_results: list | None = None,
) -> tuple[MarketService, MagicMock, MagicMock]:
    persistence = MagicMock()
    persistence.execute = AsyncMock(side_effect=persistence_results or [_obs()])
    transaction = MagicMock()
    transaction.execute = AsyncMock(
        side_effect=transaction_results
        or [
            _obs(encrypted_secret="enc"),
            _obs(address="addr"),
            _obs(network="testnet"),
            _obs(uri="solana:uri"),
        ]
    )
    return MarketService(persistence, transaction), persistence, transaction


@pytest.mark.asyncio
async def test_create_offer_returns_instructions_with_unique_memos() -> None:
    service, _, _ = _service()
    first, _ = await service.create_offer(
        item_id="i", item_name="Room", secret="s", price=150.0, currency="USDC"
    )
    service2, _, _ = _service()
    second, _ = await service2.create_offer(
        item_id="i", item_name="Room", secret="s", price=150.0, currency="USDC"
    )

    assert first.memo and second.memo
    assert first.memo != second.memo
    assert first.amount == pytest.approx(150.0)
    assert first.currency == "USDC"


@pytest.mark.asyncio
async def test_create_offer_fails_loudly_when_encryption_fails() -> None:
    service, _, _ = _service(transaction_results=[_obs(success=False, error="no key")])

    with pytest.raises(ValueError, match="Encryption failed"):
        await service.create_offer(
            item_id="i", item_name="Room", secret="s", price=1.0, currency="USDC"
        )


@pytest.mark.asyncio
async def test_check_status_unknown_deal_is_not_found() -> None:
    service, _, _ = _service(persistence_results=[_obs(success=False)])

    assert (await service.check_status(str(uuid.uuid4()))).status == "NOT_FOUND"


@pytest.mark.asyncio
async def test_check_status_expired_deal_transitions_and_reports() -> None:
    past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    deal = {
        "status": "PENDING",
        "expires_at": past,
        "final_price": 1.0,
        "payment_memo": "m",
        "currency": "USDC",
    }
    service, persistence, _ = _service(persistence_results=[_obs(**deal), _obs()])

    assert (await service.check_status(str(uuid.uuid4()))).status == "EXPIRED"
    intents = [c.args[0] for c in persistence.execute.await_args_list]
    assert "update_deal_status" in intents


@pytest.mark.asyncio
async def test_check_status_pending_without_proof_stays_pending() -> None:
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    deal = {
        "status": "PENDING",
        "expires_at": future,
        "final_price": 1.0,
        "payment_memo": "m",
        "currency": "USDC",
    }
    service, _, transaction = _service(
        persistence_results=[_obs(**deal)],
        transaction_results=[
            _obs(success=False),
            _obs(address="addr"),
            _obs(network="testnet"),
        ],
    )

    assert (await service.check_status(str(uuid.uuid4()))).status == "PENDING"
    intents = [c.args[0] for c in transaction.execute.await_args_list]
    assert "verify_settlement" in intents


def test_secret_encryption_round_trip() -> None:
    from cryptography.fernet import Fernet

    enc = SecretEncryption(Fernet.generate_key().decode())

    assert enc.decrypt(enc.encrypt("deal-secret")) == "deal-secret"


def test_secret_encryption_rejects_garbage_key() -> None:
    with pytest.raises(ValueError, match="Invalid encryption key"):
        SecretEncryption("not-a-key")
