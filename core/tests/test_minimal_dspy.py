import os

import pytest
from src.hive.proteins.reasoning.enzymes.reasoning_engine import AuraNegotiator


@pytest.fixture
def mock_dspy_lm(monkeypatch):
    """Bypass live API calls if MISTRAL_API_KEY is missing."""
    if not os.getenv("MISTRAL_API_KEY"):
        import dspy
        lm = dspy.LM("mistral/mistral-large-latest", api_key="mock")
        monkeypatch.setattr("dspy.settings.lm", lm)
        return lm
    return None

def test_aura_negotiator_init():
    negotiator = AuraNegotiator()
    assert hasattr(negotiator, "negotiate")
    assert negotiator.negotiate.signature.instructions is not None

@pytest.mark.asyncio
async def test_aura_negotiator_mock_call(mocker, mock_dspy_lm):
    negotiator = AuraNegotiator()

    # Mock the underlying dspy.Predict call to avoid real LLM interaction
    mock_prediction = mocker.Mock()
    mock_prediction.thought = "Thinking..."
    mock_prediction.action = '{"action": "accept", "price": 100, "message": "Deal"}'

    mocker.patch.object(negotiator.negotiate, "forward", return_value=mock_prediction)

    result = negotiator.forward(input_bid=100.0, context={"floor_price": 80.0})

    assert result["thought"] == "Thinking..."
    assert result["action"]["action"] == "accept"
    assert result["action"]["price"] == 100
