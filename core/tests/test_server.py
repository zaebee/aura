import pytest
from unittest.mock import AsyncMock, MagicMock
from server import NegotiationService
from aura_core import MetabolicLoop, Observation
from hive.proto.aura.negotiation.v1 import negotiation_pb2

@pytest.mark.asyncio
async def test_negotiation_service_negotiate():
    from aura_core.gen.aura.dna.v1 import NegotiationObservation
    mock_metabolism = MagicMock(spec=MetabolicLoop)
    mock_metabolism.execute = AsyncMock(return_value=Observation(success=True, negotiation=NegotiationObservation(session_token="test-token")))

    service = NegotiationService(metabolism=mock_metabolism)

    request = negotiation_pb2.NegotiateRequest(item_id="item1", bid_amount=100.0)
    context = MagicMock()
    context.invocation_metadata.return_value = [("x-request-id", "test-req-id")]

    response = await service.Negotiate(request, context)
    assert response.session_token == "test-token"
    mock_metabolism.execute.assert_called_once()

@pytest.mark.asyncio
async def test_negotiation_service_get_system_status():
    mock_metabolism = MagicMock(spec=MetabolicLoop)
    from aura_core import SystemVitals
    from aura_core.gen.aura.dna.v1 import VitalsStatus
    mock_aggregator = MagicMock()
    mock_aggregator.get_vitals = AsyncMock(return_value=SystemVitals(status=VitalsStatus.VITALS_STATUS_OK, cpu_usage_percent=15.0))
    mock_metabolism.aggregator = mock_aggregator

    service = NegotiationService(metabolism=mock_metabolism)

    request = negotiation_pb2.GetSystemStatusRequest()
    context = MagicMock()

    response = await service.GetSystemStatus(request, context)
    assert response.status == "VITALS_STATUS_OK"
    assert response.cpu_usage_percent == 15.0
