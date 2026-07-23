"""Tests for MCPEffector — background hive-event handling."""

from types import SimpleNamespace

import pytest
from aura_core_gen.aura.core.v1 import Event

from aura_mcp.effector import MCPEffector
from aura_mcp.translator import MCPTranslator


@pytest.mark.asyncio
async def test_run_without_nats_client_returns_early():
    # No NATS client -> should log a warning and return without raising.
    await MCPEffector(nats_client=None).run()


@pytest.mark.asyncio
async def test_process_event_parses_valid_proto():
    event = Event(topic="aura.hive.events.negotiation")
    msg = SimpleNamespace(data=bytes(event), subject="aura.hive.events.negotiation")
    # Should parse and log without raising.
    await MCPEffector(translator=MCPTranslator())._process_event(msg)


@pytest.mark.asyncio
async def test_process_event_swallows_malformed_data():
    # Undecodable payload must be caught, not propagated (background worker).
    msg = SimpleNamespace(data=b"\xff\xffnot-a-proto", subject="aura.hive.events.x")
    await MCPEffector(translator=MCPTranslator())._process_event(msg)
