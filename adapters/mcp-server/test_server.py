#!/usr/bin/env python3
"""
Test script for Aura MCP Server

This script tests the basic functionality of the MCP server without requiring
the actual MCP SDK to be installed.
"""

import asyncio
import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_imports():
    """Test that all required imports work."""
    print("🧪 Testing imports...")

    try:
        from agent_identity import AgentWallet

        print("✅ AgentWallet imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import AgentWallet: {e}")
        return False

    try:
        import httpx

        print("✅ httpx imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import httpx: {e}")
        return False

    try:
        from dotenv import load_dotenv

        print("✅ dotenv imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import dotenv: {e}")
        return False

    return True


async def test_wallet_generation():
    """Test that wallet generation works correctly."""
    print("\n🧪 Testing wallet generation...")

    try:
        from agent_identity import AgentWallet

        wallet = AgentWallet()
        print(f"✅ Wallet generated successfully")
        print(f"   DID: {wallet.did}")
        print(f"   Public Key: {wallet.public_key_hex}")
        print(f"   Private Key: {wallet.private_key_hex[:16]}...")

        # Test signing
        agent_id, timestamp, signature = wallet.sign_request(
            "POST", "/v1/test", {"test": "data"}
        )
        print(f"✅ Request signing works")
        print(f"   Agent ID: {agent_id}")
        print(f"   Timestamp: {timestamp}")
        print(f"   Signature: {signature[:16]}...")

        return True

    except Exception as e:
        print(f"❌ Wallet test failed: {e}")
        return False


async def test_http_client():
    """Test that HTTP client can be initialized."""
    print("\n🧪 Testing HTTP client...")

    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            # Test a simple request to see if client works
            # We'll just test that it can be created and closed
            print("✅ HTTP client initialized successfully")

        return True

    except Exception as e:
        print(f"❌ HTTP client test failed: {e}")
        return False


def test_environment():
    """Test environment variable loading."""
    print("\n🧪 Testing environment variables...")

    try:
        from dotenv import load_dotenv

        load_dotenv()

        gateway_url = os.getenv("AURA_GATEWAY_URL", "http://localhost:8000")
        mcp_host = os.getenv("MCP_HOST", "0.0.0.0")
        mcp_port = os.getenv("MCP_PORT", "8080")

        print(f"✅ Environment variables loaded")
        print(f"   AURA_GATEWAY_URL: {gateway_url}")
        print(f"   MCP_HOST: {mcp_host}")
        print(f"   MCP_PORT: {mcp_port}")

        return True

    except Exception as e:
        print(f"❌ Environment test failed: {e}")
        return False


async def test_server_initialization():
    """Test that the server can be initialized (without starting MCP)."""
    print("\n🧪 Testing server initialization...")

    try:
        # Import the server module
        from server import AuraMCPServer

        # Create server instance (this will fail if MCP is not installed)
        server = AuraMCPServer()

        print("✅ Server initialized successfully")
        print(f"   Wallet DID: {server.wallet.did}")
        print(f"   HTTP Client: {type(server.client).__name__}")

        # Clean up
        await server.shutdown()

        return True

    except ImportError as e:
        if "mcp" in str(e).lower():
            print("⚠️  MCP package not installed (expected for basic tests)")
            print("   Install with: pip install mcp")
            return True  # This is expected if MCP isn't installed
        else:
            print(f"❌ Unexpected import error: {e}")
            return False
    except Exception as e:
        print(f"❌ Server initialization failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("🔍 Running Aura MCP Server Tests\n")

    tests = [
        test_imports,
        test_environment,
        test_wallet_generation,
        test_http_client,
        test_server_initialization,
    ]

    results = []

    # Run synchronous tests first
    for test in [test_imports, test_environment]:
        results.append(test())

    # Run async tests
    for test in [test_wallet_generation, test_http_client, test_server_initialization]:
        results.append(await test())

    # Summary
    passed = sum(results)
    total = len(results)

    print(f"\n📊 Test Results: {passed}/{total} passed")

    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
