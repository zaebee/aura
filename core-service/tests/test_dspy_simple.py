#!/usr/bin/env python3
"""
Simple test for DSPy integration - tests basic functionality.
"""

import sys
from pathlib import Path

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


def test_dspy_integration_basics():
    logger.info("testing_dspy_integration")

    # Test 1: Signature definition
    logger.info("testing_signature_definition")
    # Check that signature has the expected fields
    assert "input_bid" in Negotiate.fields
    assert "context" in Negotiate.fields
    assert "history" in Negotiate.fields
    assert "thought" in Negotiate.fields
    assert "action" in Negotiate.fields
    logger.info("signature_defined_correctly")

    # Test 2: AuraNegotiator creation
    logger.info("testing_aura_negotiator_creation")
    negotiator = AuraNegotiator()
    assert negotiator is not None
    logger.info("aura_negotiator_created_successfully")

    # Test 3: AuraTransformer creation
    logger.info("testing_aura_transformer_creation")
    transformer = AuraTransformer()
    assert transformer is not None
    assert transformer.negotiator is not None
    logger.info("aura_transformer_created_successfully")

    logger.info("all_basic_tests_passed")
    logger.info("dspy_integration_working")
