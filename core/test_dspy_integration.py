#!/usr/bin/env python3
"""
Test script for DSPy integration.

Tests the basic functionality of the DSPy strategy without requiring
full service infrastructure.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def test_signature_creation():
    """Test that DSPy signature is properly defined."""
    logger.info("testing_dspy_signature_creation")

    # Test that the signature class exists and has fields
    # In DSPy 2.x, fields might not be directly on the class via hasattr
    # but we can check the signature definition
    assert "input_bid" in Negotiate.fields
    assert "context" in Negotiate.fields
    assert "history" in Negotiate.fields
    assert "thought" in Negotiate.fields
    assert "action" in Negotiate.fields

    # Test that we can create the signature (DSPy signatures don't need instantiation like this)
    # Instead, we test that the class is properly defined
    # Note: We can't test issubclass without importing dspy, but we've verified the fields above

    logger.info("dspy_signature_defined_correctly")


def test_negotiator_module():
    """Test that AuraNegotiator module can be instantiated."""
    logger.info("testing_aura_negotiator_module")

    try:
        negotiator = AuraNegotiator()
        assert negotiator is not None
        assert hasattr(negotiator, "negotiate_chain")
        logger.info("aura_negotiator_module_created_successfully")
    except Exception as e:
        logger.error("aura_negotiator_creation_failed", error=str(e))
        return False

    return True


def test_dspy_strategy_initialization():
    """Test DSPy strategy initialization."""
    logger.info("testing_dspy_strategy_initialization")

    try:
        # Create a temporary compiled program for testing
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp.write(b'{"test": "data"}')
            tmp_path = tmp.name

        # Mock the loading to avoid file issues
        with patch("llm.dspy_strategy.dspy.load") as mock_load:
            mock_load.return_value = AuraNegotiator()

            strategy = DSPyStrategy(compiled_program_path=tmp_path)
            assert strategy is not None
            assert strategy.negotiator is not None

        logger.info("dspy_strategy_initialized_successfully")

        # Clean up
        Path(tmp_path).unlink()

    except Exception as e:
        logger.error("dspy_strategy_initialization_failed", error=str(e))
        return False

    return True


def test_strategy_fallback():
    """Test fallback mechanism."""
    logger.info("testing_fallback_mechanism")

    try:
        strategy = DSPyStrategy()

        # Test that fallback strategy can be obtained
        fallback = strategy._get_fallback_strategy()
        assert fallback is not None

        logger.info("fallback_mechanism_works_correctly")

    except Exception as e:
        logger.error("fallback_mechanism_test_failed", error=str(e))
        return False

    return True


def test_context_creation():
    """Test context creation for DSPy module."""
    logger.info("testing_context_creation")

    try:
        strategy = DSPyStrategy()

        # Create a mock item
        mock_item = MagicMock()
        mock_item.id = "test_item"
        mock_item.base_price = 1000.0
        mock_item.floor_price = 800.0
        mock_item.meta = {}

        context = strategy._create_standard_context(mock_item)

        assert context["base_price"] == 1000.0
        assert context["floor_price"] == 800.0
        assert context["item_id"] == "test_item"
        assert "internal_cost" in context
        assert "value_add_inventory" in context
        assert len(context["value_add_inventory"]) == 3

        logger.info("context_creation_works_correctly")

    except Exception as e:
        logger.error("context_creation_test_failed", error=str(e))
        return False

    return True


def run_all_tests():
    """Run all integration tests."""
    logger.info("running_dspy_integration_tests")

    tests = [
        test_signature_creation,
        test_negotiator_module,
        test_dspy_strategy_initialization,
        test_strategy_fallback,
        test_context_creation,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            result = test()
            if result is False:
                failed += 1
            else:
                passed += 1
        except Exception as e:
            logger.error("test_failed_with_exception", test=test.__name__, error=str(e))
            failed += 1

    logger.info("test_results", passed=passed, failed=failed)

    if failed == 0:
        logger.info("all_tests_passed")
        return True
    else:
        logger.error("some_tests_failed")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
