#!/usr/bin/env python3
"""
Simple test for DSPy integration - tests basic functionality.
"""

import sys

import structlog
from llm.dspy_strategy import DSPyStrategy
from llm.engine import AuraNegotiator
from llm.signatures import Negotiate

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger(__name__)


def main():
    logger.info("testing_dspy_integration")

    # Test 1: Signature definition
    logger.info("testing_signature_definition")
    # Check that signature has the expected fields
    assert "input_bid" in Negotiate.input_fields
    assert "context" in Negotiate.input_fields
    assert "history" in Negotiate.input_fields
    assert "thought" in Negotiate.output_fields
    assert "action" in Negotiate.output_fields
    logger.info("signature_defined_correctly")

    # Test 2: AuraNegotiator creation
    logger.info("testing_aura_negotiator_creation")
    negotiator = AuraNegotiator()
    assert negotiator is not None
    logger.info("aura_negotiator_created_successfully")

    # Test 3: DSPyStrategy creation
    logger.info("testing_dspy_strategy_creation")
    strategy = DSPyStrategy()
    assert strategy is not None
    assert strategy.negotiator is not None
    logger.info("dspy_strategy_created_successfully")

    # Test 4: Fallback mechanism
    logger.info("testing_fallback_mechanism")
    fallback = strategy._get_fallback_strategy()
    assert fallback is not None
    logger.info("fallback_mechanism_works")

    logger.info("all_basic_tests_passed")
    logger.info("dspy_integration_working")

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error("test_failed", error=str(e))
        import traceback

        traceback.print_exc()
        sys.exit(1)
