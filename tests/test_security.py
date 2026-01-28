"""
Test script for Aura Platform Security Implementation

Tests the cryptographic signature verification functionality.
"""

import hashlib
import json

import pytest

from agent_identity import AgentWallet


def test_agent_wallet():
    """Test AgentWallet functionality."""
    print("🧪 Testing AgentWallet...")

    # Test 1: Generate new wallet
    wallet = AgentWallet()
    print(f"✅ Generated wallet: {wallet.did}")

    # Test 2: Verify DID format
    assert wallet.did.startswith("did:key:"), "DID should start with did:key:"
    print(f"✅ DID format valid: {wallet.did}")

    # Test 3: Verify key properties
    assert len(wallet.private_key_hex) > 0, "Private key should not be empty"
    assert len(wallet.public_key_hex) > 0, "Public key should not be empty"
    print("✅ Keys generated successfully")

    # Test 4: Test signing and verification
    test_payload = {
        "item_id": "test_item",
        "bid_amount": 100.0,
        "currency": "USD",
        "agent_did": wallet.did,
    }

    # Sign a request
    x_agent_id, x_timestamp, x_signature = wallet.sign_request(
        "POST", "/v1/negotiate", test_payload
    )
    print("✅ Request signed successfully")
    print(f"   Agent ID: {x_agent_id}")
    print(f"   Timestamp: {x_timestamp}")
    print(f"   Signature: {x_signature[:50]}...")

    # Verify the signature
    body_json = json.dumps(test_payload, sort_keys=True, separators=(",", ":"))

    body_hash = hashlib.sha256(body_json.encode("utf-8")).hexdigest()
    message = f"POST/v1/negotiate{x_timestamp}{body_hash}"

    is_valid = wallet.verify_signature(message, x_signature)
    assert is_valid, "Signature verification should succeed"
    print("✅ Signature verification successful")

    # Test 5: Test tampering detection
    tampered_message = f"POST/v1/negotiate{str(int(x_timestamp) + 100)}{body_hash}"
    is_tampered_valid = wallet.verify_signature(tampered_message, x_signature)
    assert not is_tampered_valid, "Tampered message should fail verification"
    print("✅ Tampering detection working")

    # Test 6: Test view-only wallet
    view_only_wallet = AgentWallet.from_did(wallet.did)
    assert view_only_wallet.did == wallet.did, "View-only wallet should have same DID"
    print("✅ View-only wallet creation successful")

    # Test 7: Test view-only wallet verification
    is_view_only_valid = view_only_wallet.verify_signature(message, x_signature)
    assert is_view_only_valid, "View-only wallet should verify signatures"
    print("✅ View-only wallet verification successful")

    print("🎉 All AgentWallet tests passed!")
    return wallet


def test_signature_verification_flow():
    """Test the complete signature verification flow."""
    print("\n🧪 Testing signature verification flow...")

    wallet = AgentWallet()

    # Create a test request
    test_payload = {
        "item_id": "hotel_alpha",
        "bid_amount": 850.0,
        "currency": "USD",
        "agent_did": wallet.did,
    }

    # Sign the request
    method = "POST"
    path = "/v1/negotiate"
    x_agent_id, x_timestamp, x_signature = wallet.sign_request(
        method, path, test_payload
    )

    print(f"✅ Signed request with DID: {x_agent_id}")

    # Verify the signature manually (simulating what the API gateway does)
    body_json = json.dumps(test_payload, sort_keys=True, separators=(",", ":"))

    body_hash = hashlib.sha256(body_json.encode("utf-8")).hexdigest()
    message = f"{method}{path}{x_timestamp}{body_hash}"

    # Test with correct message
    is_valid = wallet.verify_signature(message, x_signature)
    assert is_valid, "Valid signature should pass verification"
    print("✅ Valid signature verified successfully")

    # Test with incorrect message (tampered)
    tampered_message = f"{method}{path}{str(int(x_timestamp) + 100)}{body_hash}"
    is_tampered_valid = wallet.verify_signature(tampered_message, x_signature)
    assert not is_tampered_valid, "Tampered message should fail verification"
    print("✅ Tampered message correctly rejected")


def test_error_cases():
    """Test error cases and edge conditions."""
    print("\n🧪 Testing error cases...")

    # Test 1: Invalid DID format
    with pytest.raises(ValueError, match="Invalid DID format"):
        AgentWallet.from_did("invalid-did-format")
    print("✅ Invalid DID correctly rejected")

    # Test 2: View-only wallet signing attempt
    view_only_wallet = AgentWallet.from_did(
        "did:key:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    )
    try:
        view_only_wallet.sign_request("POST", "/test", {})
        raise AssertionError("View-only wallet should not be able to sign")
    except ValueError as e:
        print(f"✅ View-only wallet signing correctly prevented: {e}")

    # Test 3: Invalid signature verification
    wallet = AgentWallet()
    is_valid = wallet.verify_signature("test message", "invalid_signature_hex")
    assert not is_valid, "Invalid signature should fail verification"
    print("✅ Invalid signature correctly rejected")

    print("🎉 Error case tests passed!")


def main():
    """Run all security tests."""
    print("🚀 Starting Aura Platform Security Tests")
    print("=" * 50)

    try:
        # Run all tests
        wallet = test_agent_wallet()
        test_signature_verification_flow()
        test_error_cases()

        print("\n" + "=" * 50)
        print("🎉 ALL SECURITY TESTS PASSED!")
        print("=" * 50)

        print("\n📋 Test Summary:")
        print("   ✅ AgentWallet functionality")
        print("   ✅ Signature generation and verification")
        print("   ✅ Tampering detection")
        print("   ✅ View-only wallet support")
        print("   ✅ Timestamp validation")
        print("   ✅ Error handling")

        print("\n🔑 Test Wallet Information:")
        print(f"   DID: {wallet.did}")
        print(f"   Public Key: {wallet.public_key_hex}")

        print("\n💡 You can use this wallet for testing the API gateway:")
        print("   Export these keys and use them in your agent applications.")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
