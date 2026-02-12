import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aura_worker.metabolism.main import MetabolicLoop
from nats.aio.msg import Msg


@pytest.mark.asyncio
async def test_vision_rpc_handler():
    # 1. Setup mocks
    mock_node = MagicMock()
    mock_node.analyze_vision = AsyncMock(return_value={"make": "Tesla", "model": "Model 3"})

    metabolism = MetabolicLoop(worker_name="test-worker", node=mock_node)

    # Mock NATS message
    mock_msg = MagicMock(spec=Msg)
    payload = {
        "image": base64.b64encode(b"fake-image-bytes").decode(),
        "prompt": "Identify this car"
    }
    mock_msg.data = json.dumps(payload).encode()
    mock_msg.respond = AsyncMock()

    # 2. Execute handler
    await metabolism._handle_vision_request(mock_msg)

    # 3. Assertions
    mock_node.analyze_vision.assert_called_once_with([b"fake-image-bytes"], "Identify this car")

    # Check response
    respond_args = mock_msg.respond.call_args[0][0]
    response_data = json.loads(respond_args.decode())
    assert response_data["make"] == "Tesla"
    assert response_data["model"] == "Model 3"

if __name__ == "__main__":
    asyncio.run(test_vision_rpc_handler())
    print("✅ test_vision_rpc_handler passed!")
