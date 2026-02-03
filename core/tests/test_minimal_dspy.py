#!/usr/bin/env python3
"""
Minimal DSPy test to isolate the issue.
"""

import json
import os
import sys
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

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


def test_minimal_dspy():
    """Test minimal DSPy functionality."""
    logger.info("testing_minimal_dspy")

    # Check for API key to decide whether to mock or call real API
    api_key = os.environ.get("MISTRAL_API_KEY")

    # Configure DSPy
    if api_key:
        dspy.configure(lm=dspy.LM(model="mistral/mistral-large-latest"))
    else:
        logger.info("no_api_key_found_using_mock")

    # Create a simple example
    _simple_example = dspy.Example(
        input_bid="100",
        context=json.dumps(
            {
                "base_price": 200,
                "floor_price": 150,
                "occupancy": "high",
                "value_add_inventory": [],
            }
        ),
        history="[]",
    ).with_inputs("input_bid", "context", "history")

    # Create negotiator
    negotiator = AuraNegotiator()

    # Test prediction
    try:
        # Use a context manager to conditionally mock the internal DSPy call
        # This avoids network requests in CI when MISTRAL_API_KEY is missing
        cm = patch.object(negotiator, "negotiate") if not api_key else nullcontext()

        with cm as mock_predict:
            if not api_key:
                mock_predict.return_value = MagicMock(
                    thought="Mocked: Bid is below floor price, but let's test the flow.",
                    action='{"action": "counter", "price": 160.0, "message": "We can offer 160."}',
                )

            prediction = negotiator(
                input_bid="100",
                context={
                    "base_price": 200,
                    "floor_price": 150,
                    "occupancy": "high",
                    "value_add_inventory": [],
                },
                history=[],
            )

        logger.info(
            "prediction_successful",
            response_type=str(type(prediction["action"])),
            response_value=prediction["action"],
            reasoning=prediction["thought"][:50],
        )

    except Exception as e:
        logger.error("prediction_failed", error=str(e))
        import traceback

        traceback.print_exc()
        raise e


if __name__ == "__main__":
    success = test_minimal_dspy()
    sys.exit(0 if success else 1)
