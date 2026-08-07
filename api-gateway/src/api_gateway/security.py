"""
Security Module for Aura Platform API Gateway

Implements cryptographic signature verification for incoming requests.
Public Membrane provides an API-key shortcut for trusted browser origins.
"""

import hashlib
import json
import logging
import secrets
import time

import nacl.encoding
import nacl.exceptions
import nacl.signing
from fastapi import Header, HTTPException, Request

logger = logging.getLogger(__name__)

# Configuration constants
TIMESTAMP_TOLERANCE_SECONDS = 60  # Allow ±60 seconds for clock skew


async def _parse_request_body(request: Request) -> bytes:
    """Read body bytes, parse JSON if applicable, and cache in request.state.parsed_body.

    Reads from scope["body_cache"] set by BodyCachingMiddleware to avoid
    RuntimeError("Stream consumed") when File(...) params consume the stream
    before this dependency runs.

    Returns raw body bytes for callers that need them (e.g. for signature hashing).
    Raises HTTPException 400 on malformed JSON.
    """
    # Use body cached by BodyCachingMiddleware (stored in ASGI scope).
    # Falls back to b"" (safe: produces 401 not 500) if middleware not active.
    body_bytes: bytes = request.scope.get("body_cache", b"")

    content_type = request.headers.get("content-type", "")
    if body_bytes and "application/json" in content_type:
        try:
            request.state.parsed_body = json.loads(body_bytes.decode("utf-8"))
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from None
    else:
        request.state.parsed_body = {}

    return body_bytes


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
        body_bytes = await _parse_request_body(request)
        content_type = request.headers.get("content-type", "")

        if body_bytes:
            if "application/json" in content_type:
                # Canonical JSON form for deterministic hashing
                body_canonical = json.dumps(
                    request.state.parsed_body, sort_keys=True, separators=(",", ":")
                )
                body_hash = hashlib.sha256(body_canonical.encode("utf-8")).hexdigest()
            else:
                # For multipart/form-data or other types, hash the raw bytes
                body_hash = hashlib.sha256(body_bytes).hexdigest()
        else:
            body_hash = hashlib.sha256(b"").hexdigest()

        # Reconstruct message: METHOD + PATH + TIMESTAMP + BODY_HASH
        message = f"{request.method}{request.url.path}{x_timestamp}{body_hash}"

        # 6. Verify the signature
        signature_bytes = bytes.fromhex(x_signature)
        verify_key.verify(message.encode("utf-8"), signature_bytes)

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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "signature_verification_internal_error: %s: %s", type(e).__name__, e
        )
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred during signature verification.",
        ) from e

    # Return the verified agent DID for use in the endpoint
    return x_agent_id


async def verify_public_membrane(
    request: Request,
    x_agent_id: str = Header(None),
    x_timestamp: str = Header(None),
    x_signature: str = Header(None),
    x_api_key: str = Header(None),
    origin: str = Header(None),
) -> str:
    """
    Public Membrane: dual-path authentication for /v1/search, /v1/negotiate,
    /v1/vision/analyze, and /v1/deals/{deal_id}/status.

    Path A — Agent (HMAC): any DID header present → full Ed25519 verification.
    Path B — Frontend (API key): trusted Origin + matching X-Api-Key header →
        gateway acts as Ribosome-Proxy, forwarding with its own DID.

    Returns the verified agent DID (or gateway DID for frontend requests).
    """
    from .config import get_settings

    settings = get_settings()

    # Path A: agent supplies DID headers → delegate to full HMAC verification
    if x_agent_id or x_timestamp or x_signature:
        return await verify_signature(request, x_agent_id, x_timestamp, x_signature)

    # Path B: check for trusted-origin + API key
    frontend_api_key = settings.frontend_api_key
    if not frontend_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing required security headers: X-Agent-ID, X-Timestamp, X-Signature",
        )

    trusted_origins = {
        o.strip() for o in settings.trusted_frontend_origins.split(",") if o.strip()
    }

    if origin not in trusted_origins:
        raise HTTPException(
            status_code=401,
            detail="Untrusted origin. Provide agent headers or use a trusted frontend origin.",
        )

    if not secrets.compare_digest(x_api_key or "", frontend_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key.")

    # Parse and cache the request body for downstream handlers
    await _parse_request_body(request)

    # Ribosome-Proxy: gateway asserts its own DID on behalf of the browser
    return settings.gateway_did


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
