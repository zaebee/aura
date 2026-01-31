"""
Test script for Aura Platform Security Implementation

Tests the cryptographic signature verification functionality.
"""

import hashlib
import json

import pytest
import structlog

from agent_identity import AgentWallet

logger = structlog.get_logger(__name__)


def test_agent_wallet():
    """Test AgentWallet functionality."""
    logger.info("testing_agent_wallet")

    # Test 1: Generate new wallet
    wallet = AgentWallet()
    logger.info("generated_wallet", did=wallet.did)

    # Test 2: Verify DID format
    assert wallet.did.startswith("did:key:"), "DID should start with did:key:"
    logger.info("did_format_valid", did=wallet.did)

    # Test 3: Verify key properties
    assert len(wallet.private_key_hex) > 0, "Private key should not be empty"
    assert len(wallet.public_key_hex) > 0, "Public key should not be empty"
    logger.info("keys_generated_successfully")

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
    logger.info("request_signed_successfully",
                agent_id=x_agent_id,
                timestamp=x_timestamp,
                signature_snippet=x_signature[:50])

    # Verify the signature
    body_json = json.dumps(test_payload, sort_keys=True, separators=(",", ":"))

    body_hash = hashlib.sha256(body_json.encode("utf-8")).hexdigest()
    message = f"POST/v1/negotiate{x_timestamp}{body_hash}"

    is_valid = wallet.verify_signature(message, x_signature)
    assert is_valid, "Signature verification should succeed"
    logger.info("signature_verification_successful")

    # Test 5: Test tampering detection
    tampered_message = f"POST/v1/negotiate{str(int(x_timestamp) + 100)}{body_hash}"
    is_tampered_valid = wallet.verify_signature(tampered_message, x_signature)
    assert not is_tampered_valid, "Tampered message should fail verification"
    logger.info("tampering_detection_working")

    # Test 6: Test view-only wallet
    view_only_wallet = AgentWallet.from_did(wallet.did)
    assert view_only_wallet.did == wallet.did, "View-only wallet should have same DID"
    logger.info("view_only_wallet_creation_successful")

    # Test 7: Test view-only wallet verification
    is_view_only_valid = view_only_wallet.verify_signature(message, x_signature)
    assert is_view_only_valid, "View-only wallet should verify signatures"
    logger.info("view_only_wallet_verification_successful")

    logger.info("all_agent_wallet_tests_passed")
    return wallet


def test_signature_verification_flow():
    """Test the complete signature verification flow."""
    logger.info("testing_signature_verification_flow")

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

    logger.info("signed_request", did=x_agent_id)

    # Verify the signature manually (simulating what the API gateway does)
    body_json = json.dumps(test_payload, sort_keys=True, separators=(",", ":"))

    body_hash = hashlib.sha256(body_json.encode("utf-8")).hexdigest()
    message = f"{method}{path}{x_timestamp}{body_hash}"

    # Test with correct message
    is_valid = wallet.verify_signature(message, x_signature)
    assert is_valid, "Valid signature should pass verification"
    logger.info("valid_signature_verified")

    # Test with incorrect message (tampered)
    tampered_message = f"{method}{path}{str(int(x_timestamp) + 100)}{body_hash}"
    is_tampered_valid = wallet.verify_signature(tampered_message, x_signature)
    assert not is_tampered_valid, "Tampered message should fail verification"
    logger.info("tampered_message_rejected")


def test_error_cases():
    """Test error cases and edge conditions."""
    logger.info("testing_error_cases")

    # Test 1: Invalid DID format
    with pytest.raises(ValueError, match="Invalid DID format"):
        AgentWallet.from_did("invalid-did-format")
    logger.info("invalid_did_rejected")

    # Test 2: View-only wallet signing attempt
    view_only_wallet = AgentWallet.from_did(
        "did:key:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    )
    try:
        view_only_wallet.sign_request("POST", "/test", {})
        raise AssertionError("View-only wallet should not be able to sign")
    except ValueError as e:
        logger.info("view_only_signing_prevented", error=str(e))

    # Test 3: Invalid signature verification
    wallet = AgentWallet()
    is_valid = wallet.verify_signature("test message", "invalid_signature_hex")
    assert not is_valid, "Invalid signature should fail verification"
    logger.info("invalid_signature_rejected")

    logger.info("error_case_tests_passed")


def main():
    """Run all security tests."""
    # Configure logging for standalone run
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )
    logger.info("starting_security_tests")

    try:
        # Run all tests
        wallet = test_agent_wallet()
        test_signature_verification_flow()
        test_error_cases()

        logger.info("all_security_tests_passed")
        logger.info("test_summary",
                    agent_wallet=True,
                    signature_flow=True,
                    tampering_detection=True,
                    view_only_support=True,
                    error_handling=True)

        logger.info("test_wallet_info", did=wallet.did, public_key=wallet.public_key_hex)

    except Exception as e:
        logger.error("test_failed", error=str(e))
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
