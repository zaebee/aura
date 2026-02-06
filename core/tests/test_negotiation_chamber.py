from dataclasses import dataclass
from typing import Any
from unittest.mock import ANY, MagicMock

import pytest
from aura_core import Observation, SkillRegistry
from hive.chambers.negotiation.main import negotiation_loop
from hive.proto.aura.negotiation.v1 import negotiation_pb2


@dataclass
class MockSignal:
    item_id: str
    bid_amount: float
    request_id: str = "test-req"
    agent: Any = MagicMock(did="did:test")


@pytest.fixture
def mock_registry():
    registry = MagicMock(spec=SkillRegistry)

    async def mock_execute(skill, intent, params=None):
        if skill == "persistence":
            if intent == "read_item":
                return Observation(
                    success=True,
                    data={
                        "id": "test_1",
                        "name": "Atomic Core",
                        "base_price": 100.0,
                        "floor_price": 85.0,
                    },
                )
            return Observation(success=True)
        elif skill == "telemetry":
            if intent == "get_vitals":
                return Observation(
                    success=True, data={"status": "healthy", "cpu_usage_percent": 10.0}
                )
            return Observation(success=True)
        elif skill == "reasoning":
            if intent == "negotiate":
                return Observation(
                    success=True,
                    data={
                        "action": "counter",
                        "price": 95.0,
                        "message": "My best offer is 95.0",
                        "thought": "<think>Thinking...</think>",
                        "metadata": {},
                    },
                )
        elif skill == "transaction":
            if intent == "get_address":
                return Observation(success=True, data="SOL_ADDR_123")
            return Observation(success=True)
        return Observation(success=True)

    registry.execute.side_effect = mock_execute
    return registry


@pytest.mark.asyncio
async def test_negotiation_loop_hydrated(mock_registry):
    """Test the chamber loop with hydrated Proteins (SkillRegistry)."""
    signal = MockSignal(item_id="test_1", bid_amount=90.0)

    observation = await negotiation_loop(signal, mock_registry)

    assert observation.success is True
    # Verify NegotiateResponse was created
    assert isinstance(observation.data, negotiation_pb2.NegotiateResponse)
    assert observation.data.countered.proposed_price == 95.0

    # Verify pulse and telemetry were called
    mock_registry.execute.assert_any_call("pulse", "emit_negotiation", ANY)
    mock_registry.execute.assert_any_call("telemetry", "increment_counter", ANY)


@pytest.mark.asyncio
async def test_negotiation_loop_accept_flow(mock_registry):
    """Test the accept flow which triggers persistence and transaction."""
    signal = MockSignal(item_id="test_1", bid_amount=110.0)

    # Override the mock for the reasoning skill for this specific test
    original_side_effect = mock_registry.execute.side_effect

    async def mock_execute_override(skill, intent, params=None):
        if skill == "reasoning" and intent == "negotiate":
            return Observation(
                success=True,
                data={
                    "action": "accept",
                    "price": 110.0,
                    "message": "Accepted",
                    "thought": "<think>High bid!</think>",
                    "metadata": {},
                },
            )
        # Fall back to the original mock for all other calls
        return await original_side_effect(skill, intent, params)

    mock_registry.execute.side_effect = mock_execute_override

    observation = await negotiation_loop(signal, mock_registry)

    assert observation.success is True
    assert observation.event_type == "negotiation_accepted"
    assert isinstance(observation.data, negotiation_pb2.NegotiateResponse)
    assert observation.data.accepted.final_price == 110.0

    # Verify persistence.create_deal was called
    mock_registry.execute.assert_any_call("persistence", "create_deal", ANY)
