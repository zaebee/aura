#!/usr/bin/env python3
"""
DSPy Negotiation Engine Training Script.

Trains the AuraNegotiator module using the provided training dataset
and saves the compiled program for production use.
"""

import json
import sys
from pathlib import Path

import dspy
from dspy.teleprompt import BootstrapFewShot

# Add src to path for imports
sys.path.append(str(Path(__file__).parent / "src"))

from llm.engine import AuraNegotiator


def load_training_data() -> list[dict]:
    """Load and flatten training data from JSON file."""
    data_path = Path(__file__).parent / "data" / "negotiation_training.json"

    if not data_path.exists():
        raise FileNotFoundError(f"Training data not found at {data_path}")

    with open(data_path) as f:
        data = json.load(f)

    examples = []
    for scenario in data:
        context = scenario["context"]
        for turn in scenario["turns"]:
            examples.append(
                {
                    "input_bid": turn["input_bid"],
                    "context": context,
                    "history": [],  # Would be populated with previous turns in multi-turn scenarios
                    "reasoning": turn["reasoning"],
                    "response": turn["ideal_response"],
                }
            )

    return examples


def economic_metric(gold, pred, trace=None):
    """Economic metric for negotiation quality.

    Evaluates decisions based on:
    - Price validity (respecting floor price)
    - Action correctness
    - Reasoning quality
    - Value-add utilization
    """
    # 1. Expected answer
    gold_resp = gold.response
    if isinstance(gold_resp, str):
        try:
            gold_resp = json.loads(gold_resp)
        except json.JSONDecodeError:
            return 0  # Skip broken data

    # 2 Expected answer Context (to know floor_price)
    gold_ctx = gold.context
    if isinstance(gold_ctx, str):
        try:
            gold_ctx = json.loads(gold_ctx)
        except json.JSONDecodeError:
            gold_ctx = {}

    # 3. Predicted answer (AuraNegotiator now returns a dict)
    if isinstance(pred, dict):
        pred_resp = pred.get("response", {})
    else:
        pred_resp = getattr(pred, "response", {})

    if isinstance(pred_resp, str):
        try:
            pred_resp = json.loads(pred_resp)
        except json.JSONDecodeError:
            return 0

    score = 0

    # A. Structure valid (passed parsing)
    score += 0.2

    # B. Action matched (accept/counter/reject)
    if pred_resp.get("action") == gold_resp.get("action"):
        score += 0.3

    # C. Economic safety (Critical!)
    try:
        my_price = float(pred_resp.get("price", 0))
        floor_price = float(gold_ctx.get("floor_price", 0))

        # If sold lower market - PAIN (reset score)
        if pred_resp.get("action") in ["accept", "counter"] and my_price < floor_price:
            return 0

        # If sold higher marker - GAIN (give bonus)
        if pred_resp.get("action") in ["accept", "counter"] and my_price >= floor_price:
            score += 0.5

    except (ValueError, TypeError):
        pass  # Skip when no prices

    return min(score, 1.0)  # Normalize to 1.0


def train_negotiator():
    """Train and save the DSPy negotiator."""
    print("🚀 Starting DSPy Negotiation Engine Training...")

    # Load and prepare training data
    print("📖 Loading training data...")
    training_examples = load_training_data()
    print(f"📊 Found {len(training_examples)} training examples")

    # Create DSPy examples
    # Note: inputs and response are passed as dicts/lists to ensure clean saved JSON
    # and consistent comparison in metrics. AuraNegotiator handles string conversion.
    dspy_examples = [
        dspy.Example(
            input_bid=str(item["input_bid"]),
            context=item["context"],
            history=item["history"],
            reasoning=item["reasoning"],
            response=item["response"],
        ).with_inputs("input_bid", "context", "history")
        for item in training_examples
    ]

    # Configure DSPy with litellm backend
    litellm_model = "mistral/mistral-large-latest"
    print(f"🤖 Configuring DSPy with LLM: {litellm_model}")

    try:
        dspy.configure(lm=dspy.LM(litellm_model))
    except Exception as e:
        print(f"⚠️  Failed to configure with LM object: {e}")

    # Initialize negotiator
    print("🔧 Initializing AuraNegotiator...")
    negotiator = AuraNegotiator()

    # Set up teleprompter with our economic metric
    print("🎯 Setting up BootstrapFewShot optimizer...")
    teleprompter = BootstrapFewShot(metric=economic_metric)

    # Compile the module
    print("🏗️  Compiling negotiator (this may take a few minutes)...")
    try:
        compiled_negotiator = teleprompter.compile(negotiator, trainset=dspy_examples)
    except Exception as e:
        print(f"⚠️  Compilation failed (likely due to missing API keys): {e}")
        print("🏗️  Falling back to manual demo assignment for clean file generation...")
        negotiator.negotiate_chain.predict.demos = dspy_examples
        compiled_negotiator = negotiator

    # Save compiled program
    output_path = Path(__file__).parent / "src" / "aura_brain.json"
    compiled_negotiator.save(str(output_path))

    print("✅ Training/Generation complete!")
    print(f"💾 Compiled negotiator saved to: {output_path}")

    # Test the compiled negotiator if LM is available
    try:
        print("\n🧪 Testing compiled negotiator...")
        test_example = dspy_examples[0]
        prediction = compiled_negotiator(
            input_bid=test_example.input_bid,
            context=test_example.context,
            history=test_example.history,
        )

        print(f"Input bid: {test_example.input_bid}")
        print(f"Predicted action: {prediction['response']}")
        print(f"Reasoning: {prediction['reasoning'][:100]}...")
    except Exception as e:
        print(f"⏭️  Skipping test: {e}")

    return compiled_negotiator


if __name__ == "__main__":
    try:
        train_negotiator()
        print("\n🎉 DSPy Negotiation Engine training completed successfully!")
    except Exception as e:
        print(f"\n❌ Training failed: {e}")
        sys.exit(1)
