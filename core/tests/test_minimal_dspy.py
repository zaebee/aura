#!/usr/bin/env python3
"""
Minimal DSPy test to isolate the issue.
"""

import os

import dspy
import structlog
from src.hive.transformer.llm.engine import AuraNegotiator

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger(__name__)


def test_minimal_dspy(monkeypatch):
    """Test minimal DSPy functionality."""
    logger.info("testing_minimal_dspy")

    api_key = os.environ.get("MISTRAL_API_KEY")
    negotiator = AuraNegotiator()

    if api_key:
        # Temporarily configure DSPy for this test, ensuring cleanup.
        lm = dspy.LM(model="mistral/mistral-large-latest")
        monkeypatch.setattr(dspy.settings, "lm", lm)
    else:
        logger.info("no_api_key_found_using_mock")
        # Mock the internal dspy call to avoid network requests.
        mock_prediction = dspy.Prediction(
            thought="Mocked: Bid is below floor price, but let's test the flow.",
            action='{"action": "counter", "price": 160.0, "message": "We can offer 160."}',
        )
        monkeypatch.setattr(negotiator, "negotiate", lambda **kwargs: mock_prediction)

    # Execute the negotiator
    try:
        prediction = negotiator(
            input_bid=100.0,
            context={
                "base_price": 200,
                "floor_price": 150,
                "occupancy": "high",
                "value_add_inventory": [],
            },
            history=[],
        )

        # Assertions are crucial for verifying test behavior.
        assert prediction is not None
        assert "thought" in prediction
        assert isinstance(prediction["action"], dict)
        assert prediction["action"]["action"] == "counter"
        if not api_key:
            assert prediction["thought"].startswith("Mocked:")

        logger.info(
            "prediction_successful",
            response_type=str(type(prediction["action"])),
            response_value=prediction["action"],
            reasoning=prediction["thought"][:50],
        )
    except Exception as e:
        logger.error("prediction_failed", error=str(e))
        raise
