#!/usr/bin/env python3
"""
Minimal DSPy test to isolate the issue.
"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))

import dspy
from llm.engine import AuraNegotiator


def test_minimal_dspy():
    """Test minimal DSPy functionality."""
    print("🧪 Testing minimal DSPy functionality...")

    # Configure DSPy with proper LM object
    dspy.configure(lm=dspy.LM("mistral/mistral-large-latest"))

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

        print("✅ Prediction successful")
        print(f"Response type: {type(prediction.response)}")
        print(f"Response value: {prediction.response}")
        print(f"Reasoning: {prediction.reasoning[:50]}...")

        return True

    except Exception as e:
        print(f"❌ Prediction failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_minimal_dspy()
    sys.exit(0 if success else 1)
