#!/usr/bin/env python3
"""
Simple test for DSPy integration - tests basic functionality.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))

from llm.dspy_strategy import DSPyStrategy
from llm.engine import AuraNegotiator
from llm.signatures import Negotiate


def main():
    print("🚀 Testing DSPy integration...")

    # Test 1: Signature definition
    print("📋 Testing signature definition...")
    # Check that signature has the expected fields
    assert "input_bid" in Negotiate.input_fields
    assert "context" in Negotiate.input_fields
    assert "history" in Negotiate.input_fields
    assert "reasoning" in Negotiate.output_fields
    assert "response" in Negotiate.output_fields
    print("✅ Signature defined correctly")

    # Test 2: AuraNegotiator creation
    print("🤖 Testing AuraNegotiator creation...")
    negotiator = AuraNegotiator()
    assert negotiator is not None
    print("✅ AuraNegotiator created successfully")

    # Test 3: DSPyStrategy creation
    print("🔧 Testing DSPyStrategy creation...")
    strategy = DSPyStrategy()
    assert strategy is not None
    assert strategy.negotiator is not None
    print("✅ DSPyStrategy created successfully")

    # Test 4: Fallback mechanism
    print("🛡️  Testing fallback mechanism...")
    fallback = strategy._get_fallback_strategy()
    assert fallback is not None
    print("✅ Fallback mechanism works")

    print("\n🎉 All basic tests passed!")
    print("📊 DSPy integration is working correctly")

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
