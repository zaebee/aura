"""
Security Module for Aura Platform API Gateway

Implements cryptographic signature verification for incoming requests.
"""

import hashlib
import json
import time

import nacl.encoding
import nacl.exceptions
import nacl.signing
from fastapi import Header, HTTPException, Request

# Configuration constants
TIMESTAMP_TOLERANCE_SECONDS = 60  # Allow ±60 seconds for clock skew


async def verify_signature(
    request: Request,
    x_agent_id: str = Header(None),
    x_timestamp: str = Header(None),
    x_signature: str = Header(None),
) -> str:
    """
    FastAPI dependency to verify cryptographic signatures on incoming requests.

    This function validates:
    1. Presence of required security headers
    2. DID format validity
    3. Timestamp freshness (replay protection)
    4. Cryptographic signature integrity

    Args:
        request: FastAPI Request object
        x_agent_id: X-Agent-ID header (DID)
        x_timestamp: X-Timestamp header (Unix timestamp)
        x_signature: X-Signature header (hex-encoded signature)

    Returns:
        str: Verified agent DID

    Raises:
        HTTPException: 401 if verification fails
    """
    # 1. Validate required headers are present
    if not all([x_agent_id, x_timestamp, x_signature]):
        missing_headers = []
        if not x_agent_id:
            missing_headers.append("X-Agent-ID")
        if not x_timestamp:
            missing_headers.append("X-Timestamp")
        if not x_signature:
            missing_headers.append("X-Signature")

        raise HTTPException(
            status_code=401,
            detail=f"Missing required security headers: {', '.join(missing_headers)}",
        )

    # 2. Validate DID format
    if not _validate_did_format(x_agent_id):
        raise HTTPException(
            status_code=401,
            detail=f"Invalid DID format: {x_agent_id}. Expected format: did:key:public_key_hex",
        )

    # 3. Validate timestamp (prevent replay attacks)
    try:
        request_time = int(x_timestamp)
        current_time = int(time.time())
        time_diff = abs(current_time - request_time)

        # Allow requests within ±60 seconds to account for clock skew
        if time_diff > TIMESTAMP_TOLERANCE_SECONDS:
            raise HTTPException(
                status_code=401,
                detail=f"Request timestamp too old or in future. "
                f"Current: {current_time}, Request: {request_time}, "
                f"Difference: {time_diff}s (max {TIMESTAMP_TOLERANCE_SECONDS} allowed)",
            )
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid timestamp format: {x_timestamp}. Expected Unix timestamp",
        ) from None

    # 4. Extract public key from DID
    try:
        public_key_hex = x_agent_id[8:]  # Remove "did:key:" prefix
        public_key_bytes = bytes.fromhex(public_key_hex)
        verify_key = nacl.signing.VerifyKey(public_key_bytes)
    except ValueError as e:
        raise HTTPException(
            status_code=401, detail=f"Invalid public key in DID: {str(e)}"
        ) from None

    # 5. Reconstruct the signed message
    try:
        # Read and hash request body
        body_bytes = await request.body()
        if body_bytes:
            body_json = json.loads(body_bytes.decode("utf-8"))
            body_canonical = json.dumps(
                body_json, sort_keys=True, separators=(",", ":")
            )
            body_hash = hashlib.sha256(body_canonical.encode("utf-8")).hexdigest()

            # Store the parsed body in request.state for later use by FastAPI
            request.state.parsed_body = body_json
        else:
            body_hash = hashlib.sha256(b"").hexdigest()
            request.state.parsed_body = {}

        # Reconstruct message: METHOD + PATH + TIMESTAMP + BODY_HASH
        message = f"{request.method}{request.url.path}{x_timestamp}{body_hash}"

        # 6. Verify the signature
        signature_bytes = bytes.fromhex(x_signature)
        verify_key.verify(message.encode("utf-8"), signature_bytes)

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from None
    except nacl.exceptions.BadSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Invalid signature - request may have been tampered with",
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid signature format. Expected a hex-encoded string.",
        ) from None
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred during signature verification.",
        ) from None

    # Return the verified agent DID for use in the endpoint
    return x_agent_id


def _validate_did_format(did: str) -> bool:
    """
    Validate that a DID follows the expected format.

    Args:
        did: Decentralized Identifier to validate

    Returns:
        True if valid, False otherwise
    """
    if not did or not isinstance(did, str):
        return False

    # Must start with "did:key:"
    if not did.startswith("did:key:"):
        return False

    # Public key part must be hex-encoded (even length, hex characters)
    public_key_part = did[8:]
    if len(public_key_part) == 0:
        return False

    try:
        # Check if it's valid hex
        bytes.fromhex(public_key_part)
        return True
    except ValueError:
        return False


# Remove the async helper function since it's not needed
# The body reading is done directly in the verify_signature function
