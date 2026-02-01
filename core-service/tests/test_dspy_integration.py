#!/usr/bin/env python3
"""
Test script for DSPy integration.

Tests the basic functionality of the AuraTransformer without requiring
full service infrastructure.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import structlog

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from hive.transformer.main import AuraTransformer
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
    assert "input_bid" in Negotiate.fields
    assert "context" in Negotiate.fields
    assert "history" in Negotiate.fields
    assert "thought" in Negotiate.fields
    assert "action" in Negotiate.fields

    logger.info("dspy_signature_defined_correctly")


def test_negotiator_module():
    """Test that AuraNegotiator module can be instantiated."""
    logger.info("testing_aura_negotiator_module")

    try:
        negotiator = AuraNegotiator()
        assert negotiator is not None
        # Check for expected components in AuraNegotiator
        assert hasattr(negotiator, "negotiate") or hasattr(negotiator, "negotiate_chain")
        logger.info("aura_negotiator_module_created_successfully")
    except Exception as e:
        logger.error("aura_negotiator_creation_failed", error=str(e))
        return False

    return True


def test_aura_transformer_initialization():
    """Test AuraTransformer initialization."""
    logger.info("testing_aura_transformer_initialization")

    try:
        # Create a temporary compiled program for testing
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp.write(b'{"test": "data"}')
            tmp_path = tmp.name

        # Mock the loading to avoid file issues
        with patch("dspy.load") as mock_load:
            mock_load.return_value = AuraNegotiator()

            transformer = AuraTransformer(compiled_program_path=tmp_path)
            assert transformer is not None
            assert transformer.negotiator is not None

        logger.info("aura_transformer_initialized_successfully")

        # Clean up
        Path(tmp_path).unlink()

    except Exception as e:
        logger.error("aura_transformer_initialization_failed", error=str(e))
        return False

    return True


def test_economic_context_creation():
    """Test economic context creation in AuraTransformer."""
    logger.info("testing_economic_context_creation")

    try:
        from aura_core.types import HiveContext, NegotiationOffer
        transformer = AuraTransformer()

        context = HiveContext(
            item_id="test_item",
            offer=NegotiationOffer(bid_amount=500.0, reputation=0.9),
            item_data={
                "base_price": 1000.0,
                "floor_price": 800.0,
                "meta": {"perk": "free_wifi"}
            },
            system_health={"cpu_usage_percent": 10.0}
        )

        eco_context = transformer._build_economic_context(context)

        assert eco_context["base_price"] == 1000.0
        assert eco_context["floor_price"] == 800.0
        assert eco_context["reputation"] == 0.9
        assert eco_context["meta"]["perk"] == "free_wifi"
        assert "system_constraints" in eco_context

        logger.info("economic_context_creation_works_correctly")

    except Exception as e:
        logger.error("economic_context_creation_test_failed", error=str(e))
        return False

    return True


def run_all_tests():
    """Run all integration tests."""
    logger.info("running_dspy_integration_tests")

    tests = [
        test_signature_creation,
        test_negotiator_module,
        test_aura_transformer_initialization,
        test_economic_context_creation,
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
