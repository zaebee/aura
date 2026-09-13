"""Solana payment verification over fabricated chain data — no network.

`SolanaProvider` talks to RPC through httpx (`_get_signatures`, `_get_tx`);
the matching itself (`_check_sol`, `_check_usdc`, `_check_match`) is pure
dict logic over `jsonParsed` transaction shapes. These tests pin the
matching: exact amounts within tolerance, exact memos, and every
not-found shape returning None instead of raising.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aura_hive.hive.proteins.transaction.solana_engine import (
    AMOUNT_TOLERANCE,
    SolanaProvider,
)

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Fixed test keypair (seed 0..31): deterministic, never touches a network.
# base58 is not a project dependency, so the encoded secret is baked in
# rather than derived at import time.
TEST_KEY_B58 = "1GMkH3brNXiNNs1tiFZHu4yZSRrzJwxi5wB9bHFtMikjwpAW9DMZzU2Pqakc5it8X3N5vPmqdN7KF4CCUpmKhq"


def _provider() -> SolanaProvider:
    provider = SolanaProvider(
        private_key_base58=TEST_KEY_B58,
        rpc_url="http://localhost:8899",
        usdc_mint=USDC_MINT,
    )
    provider.client = MagicMock()
    provider.client.post = AsyncMock()
    return provider


def _sol_tx(memo: str, lamports_delta: int, sender: str = "sender-addr") -> dict:
    me = "ME"
    return {
        "slot": 123,
        "blockTime": 1700000000,
        "transaction": {
            "message": {
                "accountKeys": [me, sender],
                "instructions": [{"program": "spl-memo", "parsed": memo}],
            }
        },
        "meta": {
            "preBalances": [1_000_000_000, 5_000_000_000],
            "postBalances": [
                1_000_000_000 + lamports_delta,
                5_000_000_000 - lamports_delta,
            ],
        },
    }


def _usdc_tx(
    memo: str, amount_raw: int, dest: str, authority: str = "auth-addr"
) -> dict:
    return {
        "slot": 124,
        "blockTime": 1700000001,
        "transaction": {
            "message": {
                "accountKeys": [],
                "instructions": [
                    {"program": "spl-memo", "parsed": memo},
                    {
                        "program": "spl-token",
                        "parsed": {
                            "type": "transfer",
                            "info": {
                                "destination": dest,
                                "amount": str(amount_raw),
                                "authority": authority,
                            },
                        },
                    },
                ],
            }
        },
        "meta": {},
    }


def test_check_sol_matches_exact_transfer() -> None:
    provider = _provider()
    me = str(provider.keypair.pubkey())
    tx = _sol_tx("memo-1", 1_500_000_000)
    tx["transaction"]["message"]["accountKeys"] = [me, "sender-addr"]

    matched, sender = provider._check_sol(tx, 1.5)

    assert matched is True
    assert sender == "sender-addr"


def test_check_sol_rejects_wrong_amount() -> None:
    provider = _provider()
    me = str(provider.keypair.pubkey())
    tx = _sol_tx("memo-1", 1_000_000_000)
    tx["transaction"]["message"]["accountKeys"] = [me, "sender-addr"]

    matched, _ = provider._check_sol(tx, 1.5)

    assert matched is False


def test_check_sol_rejects_wrong_memo_via_match() -> None:
    provider = _provider()
    me = str(provider.keypair.pubkey())
    tx = _sol_tx("other-memo", 1_500_000_000)
    tx["transaction"]["message"]["accountKeys"] = [me, "sender-addr"]

    matched, _ = provider._check_match(tx, 1.5, "memo-1", "SOL")

    assert matched is False


def test_check_usdc_matches_stablecoin_transfer() -> None:
    provider = _provider()
    dest = str(provider.usdc_token_account)
    tx = _usdc_tx("memo-9", 150_000_000, dest)

    matched, authority = provider._check_usdc(tx, 150.0)

    assert matched is True
    assert authority == "auth-addr"


def test_check_usdc_rejects_wrong_destination() -> None:
    provider = _provider()
    tx = _usdc_tx("memo-9", 150_000_000, "someone-else")

    matched, _ = provider._check_usdc(tx, 150.0)

    assert matched is False


def test_amount_tolerance_is_tight() -> None:
    assert AMOUNT_TOLERANCE == pytest.approx(0.0001)


@pytest.mark.asyncio
async def test_verify_payment_returns_none_when_nothing_matches() -> None:
    provider = _provider()
    provider.client.post = AsyncMock(
        side_effect=[
            MagicMock(json=lambda: {"result": [{"signature": "sig1"}]}),
            MagicMock(json=lambda: {"result": None}),
        ]
    )

    assert await provider.verify_payment(1.0, "memo-x", "SOL") is None


@pytest.mark.asyncio
async def test_verify_payment_finds_matching_transfer() -> None:
    provider = _provider()
    me = str(provider.keypair.pubkey())
    tx = _sol_tx("memo-7", 2_000_000_000)
    tx["transaction"]["message"]["accountKeys"] = [me, "sender-addr"]
    provider.client.post = AsyncMock(
        side_effect=[
            MagicMock(json=lambda: {"result": [{"signature": "sig9"}]}),
            MagicMock(json=lambda: {"result": tx}),
        ]
    )

    proof = await provider.verify_payment(2.0, "memo-7", "SOL")

    assert proof is not None
    assert proof["transaction_hash"] == "sig9"
    assert proof["from_address"] == "sender-addr"


@pytest.mark.asyncio
async def test_verify_payment_rpc_error_is_none_not_raise() -> None:
    provider = _provider()
    provider.client.post = AsyncMock(side_effect=RuntimeError("rpc down"))

    with pytest.raises(RuntimeError):
        await provider.verify_payment(1.0, "memo-x", "SOL")
