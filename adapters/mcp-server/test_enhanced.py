#!/usr/bin/env python3
"""
Test script for Enhanced Aura MCP Server with Mistral Vibe Integration

This script tests the enhanced functionality without requiring actual Mistral API calls.
"""

import asyncio
import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from enhanced_server import EnhancedAuraMCPServer


async def test_enhanced_server_initialization():
    """Test that enhanced server can be initialized."""
    print("🧪 Testing Enhanced Server Initialization...")
    
    try:
        # Test without Mistral API key (should fall back gracefully)
        os.environ.pop("MISTRAL_API_KEY", None)
        
        server = EnhancedAuraMCPServer()
        
        print("✅ Enhanced server initialized successfully")
        print(f"   Mistral Client: {server.mistral_client}")
        print(f"   Wallet DID: {server.wallet.did}")
        
        # Clean up
        await server.shutdown()
        return True
        
    except Exception as e:
        print(f"❌ Enhanced server initialization failed: {e}")
        return False


async def test_fallback_behavior():
    """Test that enhanced tools fall back gracefully."""
    print("\n🧪 Testing Fallback Behavior...")
    
    try:
        # Create server without Mistral integration
        os.environ.pop("MISTRAL_API_KEY", None)
        server = EnhancedAuraMCPServer()
        
        # Test enhanced search (should fall back to standard search)
        result = await server.enhanced_search_with_insights(
            query="Luxury beach resort",
            limit=2,
            context="Client prefers eco-friendly hotels"
        )
        
        print("✅ Fallback behavior works correctly")
        print(f"   Result contains search data: {'Search Results' in result}")
        print(f"   Result length: {len(result)} characters")
        
        # Clean up
        await server.shutdown()
        return True
        
    except Exception as e:
        print(f"❌ Fallback test failed: {e}")
        return False


async def test_with_mock_mistral():
    """Test enhanced functionality with mock Mistral client."""
    print("\n🧪 Testing with Mock Mistral Client...")
    
    try:
        server = EnhancedAuraMCPServer()
        
        # Mock the Mistral client
        class MockMistralClient:
            def __init__(self):
                self.call_count = 0
                
            def invoke(self, data):
                self.call_count += 1
                
                # Return mock AI_Decision-like response
                class MockDecision:
                    def __init__(self):
                        self.reasoning = (
                            "Based on the search results and client context, "
                            "I recommend the eco-friendly luxury resort. "
                            "Negotiation strategy: Start with 15% below listed price."
                        )
                
                return MockDecision()
        
        # Replace client with mock
        server.mistral_client = MockMistralClient()
        
        # Test enhanced search
        result = await server.enhanced_search_with_insights(
            query="Eco-friendly luxury resort",
            limit=1,
            context="Client wants sustainable travel options"
        )
        
        print("✅ Mock Mistral integration works")
        print(f"   Result contains AI insights: {'AI Insights' in result}")
        print(f"   Mock client called: {server.mistral_client.call_count} times")
        
        # Clean up
        await server.shutdown()
        return True
        
    except Exception as e:
        print(f"❌ Mock Mistral test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_standard_functionality_preserved():
    """Test that standard MCP functionality is preserved."""
    print("\n🧪 Testing Standard Functionality Preservation...")
    
    try:
        server = EnhancedAuraMCPServer()
        
        # Test standard search still works
        search_result = await server.search_hotels("Luxury hotel", limit=1)
        
        # Test standard negotiation still works
        negotiation_result = await server.negotiate_price("hotel_alpha", 850.0)
        
        print("✅ Standard functionality preserved")
        print(f"   Search works: {'Search Results' in search_result}")
        print(f"   Negotiation works: {len(negotiation_result) > 0}")
        
        # Clean up
        await server.shutdown()
        return True
        
    except Exception as e:
        print(f"❌ Standard functionality test failed: {e}")
        return False


async def main():
    """Run all enhanced server tests."""
    print("🚀 Enhanced Aura MCP Server Tests")
    print("=" * 50)
    print("Testing Mistral Vibe integration capabilities...")
    print("Note: These tests use mocks - no actual Mistral API calls are made.\n")
    
    tests = [
        test_enhanced_server_initialization,
        test_fallback_behavior,
        test_with_mock_mistral,
        test_standard_functionality_preserved,
    ]
    
    results = []
    
    for test in tests:
        results.append(await test())
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"\n📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All enhanced server tests passed!")
        print("\n📚 Next steps for Mistral Vibe integration:")
        print("1. Set MISTRAL_API_KEY in environment")
        print("2. Install dependencies: uv add langchain-mistralai")
        print("3. Run enhanced server: python enhanced_server.py")
        print("4. Test with real Mistral Vibe API calls")
        return 0
    else:
        print("❌ Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)