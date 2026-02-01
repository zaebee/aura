#!/usr/bin/env python3
"""
Minimal DSPy test to isolate the issue.
"""

import json
import sys
from pathlib import Path

# Add src to path

import dspy
import structlog
from llm.engine import AuraNegotiator

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

    # Configure DSPy with proper LM object
    dspy.configure(lm=dspy.LM(model="mistral/mistral-large-latest"))

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
        from unittest.mock import MagicMock, patch
        with patch.object(negotiator, 'negotiate') as mock_predict:
            mock_predict.return_value = MagicMock(
                thought="I should reject this bid as it is below floor price.",
                action='{"action": "reject", "price": 0.0, "message": "Too low."}'
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

        logger.info("prediction_successful",
                    action=prediction['action'],
                    thought=prediction['thought'][:50])

        return True

    except Exception as e:
        logger.error("prediction_failed", error=str(e))
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_minimal_dspy()
    sys.exit(0 if success else 1)
