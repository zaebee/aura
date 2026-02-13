import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch
from hive.proteins.pulse.skill import PulseSkill
from hive.proteins.pulse.engine import JetStreamProvider
from config.server import ServerSettings
from hive.metabolism.security import AuditSigner
from aura_core.gen.aura.core.v1 import Event

@pytest.mark.asyncio
async def test_pulse_skill_signing_integration():
    # 1. Setup
    settings = ServerSettings()
    settings.event_signing_key = "test-key-123"
    print(f"DEBUG: settings.event_signing_key = '{settings.event_signing_key}'")

    mock_provider = MagicMock(spec=JetStreamProvider)
    mock_provider.connect = AsyncMock(return_value=True)

    skill = PulseSkill()
    skill.bind(settings, mock_provider)

    # Verify signer was created and set on provider
    assert skill.signer is not None
    mock_provider.set_signer.assert_called_once_with(skill.signer)

    # 2. Test emit with signing
    await skill.execute("emit_heartbeat", {"service": "test"})
    mock_provider.publish_heartbeat.assert_called_once()

@pytest.mark.asyncio
async def test_jetstream_provider_signing_logic(mocker):
    # Test the internal _publish logic of JetStreamProvider
    provider = JetStreamProvider(nats_url="nats://localhost:4222")
    signer = AuditSigner("test-key")
    provider.set_signer(signer)

    # Mock NATS and JetStream
    mock_js = MagicMock()
    mock_js.publish = AsyncMock()
    provider.js = mock_js

    event = Event()
    event.topic = "test.topic"

    success = await provider._publish("test.topic", event)

    assert success is True
    # Verify mock_js.publish was called with headers
    args, kwargs = mock_js.publish.call_args
    assert "headers" in kwargs
    headers = kwargs["headers"]
    assert AuditSigner.HEADER_NAME in headers
    assert AuditSigner.TIMESTAMP_HEADER in headers
