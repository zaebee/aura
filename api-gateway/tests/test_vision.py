import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from main import app, settings
import nats

@pytest.fixture
def client():
    return TestClient(app)

@pytest.mark.asyncio
async def test_analyze_vision_endpoint():
    # 1. Setup mocks
    mock_nc = AsyncMock(spec=nats.NATS)
    mock_response = MagicMock()
    mock_response.data = json.dumps({"make": "Toyota", "model": "Camry"}).encode()
    mock_nc.request.return_value = mock_response

    # 2. Patch global nc and verify_signature dependency
    with patch("main.nc", mock_nc):
        # We override the dependency to skip signature verification for this test
        from security import verify_signature
        app.dependency_overrides[verify_signature] = lambda: "did:key:test"

        client = TestClient(app)

        # 3. Execute request
        files = {"file": ("test.jpg", b"fake-image-content", "image/jpeg")}
        data = {"focus": "car search"}

        # Headers for multipart
        response = client.post(
            "/v1/vision/analyze",
            files=files,
            data=data,
            headers={
                "X-Agent-ID": "did:key:test",
                "X-Timestamp": "1234567890",
                "X-Signature": "fake-sig"
            }
        )

        # 4. Assertions
        assert response.status_code == 200
        result = response.json()
        assert result["make"] == "Toyota"
        assert result["model"] == "Camry"
        assert result["source"] == "vision-cortex"

        # Verify NATS request was called
        mock_nc.request.assert_called_once()
        args, kwargs = mock_nc.request.call_args
        assert args[0] == "aura.worker.v1.vision.analyze"

        payload = json.loads(args[1].decode())
        assert "image" in payload
        assert payload["prompt"] == "car search"

        # Cleanup
        app.dependency_overrides = {}

if __name__ == "__main__":
    # Note: running this file directly with python might be tricky due to pytest.mark.asyncio
    # It's better to run with `pytest api-gateway/tests/test_vision.py`
    pass
