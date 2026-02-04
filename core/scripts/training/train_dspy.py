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
import structlog
from dspy.teleprompt import BootstrapFewShot
from hive.transformer.llm.engine import AuraNegotiator
from hive.transformer.llm.prepare.clean import clean_and_parse_json

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger(__name__)


def load_training_data() -> list[dict]:
    """Load and flatten training data from JSON file."""
    # Find core data directory relative to the repository root
    # This assumes the script is run from the repo root via Makefile
    data_path = Path("core/data/negotiation_training.json")

    if not data_path.exists():
        # Fallback to relative path if not run from root
        data_path = (
            Path(__file__).parent.parent.parent / "data" / "negotiation_training.json"
        )

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
                    "thought": turn["thought"],
                    "action": turn["action"],
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
    - Constraint: No markdown tags in response
    """
    # 1. Expected answer
    gold_resp = gold.action
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

    # 3. Predicted answer (AuraNegotiator returns a dict)
    if isinstance(pred, dict):
        pred_resp = pred.get("action", {})
        raw_action = pred.get("raw_action", "")
    else:
        pred_resp = getattr(pred, "action", {})
        raw_action = getattr(pred, "raw_action", "")

    # Constraint: No Markdown tags in raw output
    if isinstance(raw_action, str) and "```" in raw_action:
        return 0

    if isinstance(pred_resp, str):
        try:
            pred_resp = clean_and_parse_json(pred_resp)
        except (ValueError, json.JSONDecodeError):
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
    logger.info("starting_dspy_training")

    # Load and prepare training data
    logger.info("loading_training_data")
    training_examples = load_training_data()
    logger.info("training_data_loaded", count=len(training_examples))

    # Create DSPy examples
    # Note: inputs and action are passed as dicts/lists to ensure clean saved JSON
    # and consistent comparison in metrics. AuraNegotiator handles string conversion.
    dspy_examples = [
        dspy.Example(
            input_bid=str(item["input_bid"]),
            context=item["context"],
            history=item["history"],
            thought=item["thought"],
            action=item["action"],
        ).with_inputs("input_bid", "context", "history")
        for item in training_examples
    ]

    # Configure DSPy with litellm backend
    litellm_model = "mistral/mistral-large-latest"
    logger.info("configuring_dspy", model=litellm_model)

    try:
        dspy.configure(lm=dspy.LM(model=litellm_model))
    except Exception as e:
        logger.warning("dspy_configure_failed", error=str(e))

    # Initialize negotiator
    logger.info("initializing_negotiator")
    negotiator = AuraNegotiator()

    # Set up teleprompter with our economic metric
    logger.info("setting_up_optimizer")
    teleprompter = BootstrapFewShot(metric=economic_metric)

    # Compile the module
    logger.info("compiling_negotiator", note="this may take a few minutes")
    try:
        compiled_negotiator = teleprompter.compile(negotiator, trainset=dspy_examples)
    except Exception as e:
        logger.warning("compilation_failed", error=str(e))
        logger.info("falling_back_to_manual_demos")
        negotiator.negotiate_chain.predict.demos = dspy_examples
        compiled_negotiator = negotiator

    # Save compiled program
    output_path = Path("core/data/aura_brain.json")
    if not output_path.parent.exists():
        output_path = Path(__file__).parent.parent.parent / "data" / "aura_brain.json"

    compiled_negotiator.save(str(output_path))

    logger.info("training_complete", saved_to=str(output_path))

    # Test the compiled negotiator if LM is available
    try:
        logger.info("testing_compiled_negotiator")
        test_example = dspy_examples[0]
        prediction = compiled_negotiator(
            input_bid=test_example.input_bid,
            context=test_example.context,
            history=test_example.history,
        )

        logger.info(
            "test_prediction",
            input_bid=test_example.input_bid,
            action=prediction["action"],
            thought=prediction["thought"][:100],
        )
    except Exception as e:
        logger.info("skipping_test", error=str(e))

    return compiled_negotiator


if __name__ == "__main__":
    try:
        train_negotiator()
        logger.info("training_success")
    except Exception as e:
        logger.error("training_failed", error=str(e))
        sys.exit(1)
