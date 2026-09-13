"""Crypto end-to-end: Negotiate → Accept → Payment → Reveal, on mocks.

The whole money path without a chain or a database: offer creation,
USD→SOL conversion inside the flow, expiry, idempotent status polls,
and secret revelation after payment. If this file is green, the
wiring between MarketService, the transaction protein and persistence
holds — the units underneath have their own suites.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aura_core_gen.aura.core.google import protobuf
from aura_core_gen.aura.core.v1 import Observation
from aura_hive.hive.proteins.transaction.engine import PriceConverter
from aura_hive.hive.services.market import MarketService


def _obs(success: bool = True, **fields: Any) -> Observation:
    return Observation(
        success=success, metadata=protobuf.Struct().from_dict(dict(fields))
    )


def _service() -> tuple[MarketService, MagicMock, MagicMock]:
    persistence = MagicMock()
    persistence.execute = AsyncMock()
    transaction = MagicMock()
    transaction.execute = AsyncMock()
    return MarketService(persistence, transaction), persistence, transaction


def _fresh_deal(**overrides: object) -> dict:
    deal: dict = {
        "id": str(uuid.uuid4()),
        "status": "PENDING",
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "final_price": 1.5,
        "payment_memo": "memo-e2e",
        "currency": "SOL",
        "item_id": "item-1",
        "buyer_did": "did:key:e2e",
        "secret_content": "enc",
    }
    deal.update(overrides)
    return deal


@pytest.mark.asyncio
async def test_full_flow_negotiate_accept_payment_reveal() -> None:
    """Offer in SOL (converted from USD) → paid → secret revealed."""
    service, persistence, transaction = _service()

    sol_price = PriceConverter().convert_usd_to_crypto(150.0, "SOL")
    assert sol_price == pytest.approx(1.5)

    transaction.execute.side_effect = [
        _obs(encrypted_secret="enc"),  # encrypt_secret
        _obs(address="addr"),  # get_address
        _obs(network="testnet"),  # get_network_name
        _obs(uri="solana:uri"),  # generate_payment_request
    ]
    persistence.execute.side_effect = [_obs()]
    instructions, uri = await service.create_offer(
        item_id="item-1",
        item_name="Room",
        secret="door-code-42",
        price=sol_price,
        currency="SOL",
    )
    assert instructions.memo
    assert uri == "solana:uri"

    # Accept: settlement proof arrives, deal flips to PAID.
    deal = _fresh_deal()
    proof = {
        "transaction_hash": "txhash",
        "block_number": "1",
        "from_address": "buyer",
        "confirmed_at": datetime.now(UTC).isoformat(),
    }
    persistence.execute.side_effect = [_obs(**deal), _obs()]
    transaction.execute.side_effect = [
        _obs(**proof),  # verify_settlement
        _obs(secret="door-code-42"),  # decrypt_secret (reveal)
    ]
    resp = await service.check_status(deal["id"])
    assert resp.status == "PAID"
    expected_ts = int(datetime.fromisoformat(proof["confirmed_at"]).timestamp())
    assert resp.secret.paid_at == expected_ts
    assert resp.proof.confirmed_at == expected_ts

    intents = [c.args[0] for c in persistence.execute.await_args_list]
    assert "confirm_ground_state" in intents


@pytest.mark.asyncio
async def test_expired_offer_reports_expired() -> None:
    service, persistence, _ = _service()
    deal = _fresh_deal(
        expires_at=(datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    )
    persistence.execute.side_effect = [_obs(**deal), _obs()]

    assert (await service.check_status(deal["id"])).status == "EXPIRED"


@pytest.mark.asyncio
async def test_repeated_status_polls_are_stable() -> None:
    """Idempotent polls: same answer twice, no duplicate transitions."""
    service, persistence, transaction = _service()
    deal = _fresh_deal()
    persistence.execute.side_effect = [_obs(**deal), _obs(**deal)]
    transaction.execute.side_effect = [_obs(success=False)] * 6

    first = await service.check_status(deal["id"])
    second = await service.check_status(deal["id"])

    assert (first.status, second.status) == ("PENDING", "PENDING")
    intents = [c.args[0] for c in persistence.execute.await_args_list]
    assert "update_deal_status" not in intents
    assert "confirm_ground_state" not in intents
