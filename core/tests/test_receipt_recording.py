"""
Every decision is archived, including the ones that refused.

`MetabolicLoop` calls `connector.act` unconditionally after the outbound
Membrane, so a refusal reaches the Connector like anything else — and "you
refused me" is the likeliest dispute a counterparty brings.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    DecisionReceipt,
    HiveContextData,
    Intent,
    NegotiationIntent,
    Observation,
)
from aura_hive.hive.connector.main import HiveConnector


def a_decision(action: ActionType, token: str = "tok-abc") -> Intent:
    intent = Intent(
        action=action,
        reasoning="LLM reasoning",
        negotiation=NegotiationIntent(price=1200.0, message="offer"),
    )
    intent.dispute_token = token
    intent.receipt = DecisionReceipt(
        version="AURA-RECEIPT-V2-UNSIGNED",
        decision_id="dec-1111",
        request_id="req-2222",
        issued_at="2026-08-12T10:00:00Z",
    )
    return intent


def a_context() -> Context:
    return Context(hive=HiveContextData(request_id="req-2222"))


def connector_with(registry: MagicMock) -> HiveConnector:
    return HiveConnector(registry=registry)


def a_registry(record_result: Any = None) -> MagicMock:
    registry = MagicMock()
    registry.execute = AsyncMock(
        return_value=record_result or Observation(success=True)
    )
    return registry


class TestTheArchiveIsWritten:
    @pytest.mark.asyncio
    async def test_an_emitted_decision_is_recorded_under_its_token(self) -> None:
        registry = a_registry()

        await connector_with(registry).act(
            a_decision(ActionType.ACTION_TYPE_COUNTER), a_context()
        )

        call = next(
            c for c in registry.execute.await_args_list if c[0][1] == "record_receipt"
        )
        assert call[0][0] == "persistence"
        assert call[0][2]["dispute_token"] == "tok-abc"
        assert call[0][2]["receipt"]["decisionId"] == "dec-1111"

    @pytest.mark.asyncio
    async def test_a_refused_decision_is_recorded_too(self) -> None:
        """The dispute most likely to arrive is about a refusal."""
        registry = a_registry()

        await connector_with(registry).act(
            a_decision(ActionType.ACTION_TYPE_REJECT), a_context()
        )

        assert any(
            c[0][1] == "record_receipt" for c in registry.execute.await_args_list
        )

    @pytest.mark.asyncio
    async def test_a_decision_with_no_receipt_records_nothing(self) -> None:
        """An unwired Membrane mints none; there is nothing to archive."""
        registry = a_registry()
        intent = Intent(action=ActionType.ACTION_TYPE_COUNTER, reasoning="x")

        await connector_with(registry).act(intent, a_context())

        assert not any(
            c[0][1] == "record_receipt" for c in registry.execute.await_args_list
        )


class TestTheArchiveNeverCostsTheDecision:
    @pytest.mark.asyncio
    async def test_a_failed_write_still_returns_an_observation(self) -> None:
        registry = a_registry(Observation(success=False, error="connection refused"))

        observation = await connector_with(registry).act(
            a_decision(ActionType.ACTION_TYPE_COUNTER), a_context()
        )

        assert observation is not None

    @pytest.mark.asyncio
    async def test_a_hanging_write_is_abandoned_rather_than_waited_on(self) -> None:
        """
        The failure mode a refused connection does not cover.

        A refused connect raises in milliseconds. A blackholed one does not
        raise at all — psycopg2 sits in the kernel's TCP retry for minutes,
        serially, ahead of the decision, on every call including the refusals
        that did no database work before this change. Fail-open against
        exceptions is only half the promise.
        """
        import aura_hive.hive.connector.main as connector_main

        async def never_returns(*args: Any, **kwargs: Any) -> Any:
            await asyncio.sleep(60)

        registry = MagicMock()
        registry.execute = never_returns

        with patch.object(connector_main, "_ARCHIVE_TIMEOUT_SECONDS", 0.05):
            observation = await asyncio.wait_for(
                connector_with(registry).act(
                    a_decision(ActionType.ACTION_TYPE_COUNTER), a_context()
                ),
                timeout=5,
            )

        assert observation is not None

    @pytest.mark.asyncio
    async def test_a_raising_write_still_returns_an_observation(self) -> None:
        """
        The promise has to hold from where the code sits, not from someone
        having checked that the protein never raises.
        """
        registry = MagicMock()
        registry.execute = AsyncMock(side_effect=RuntimeError("pool exhausted"))

        observation = await connector_with(registry).act(
            a_decision(ActionType.ACTION_TYPE_COUNTER), a_context()
        )

        assert observation is not None
