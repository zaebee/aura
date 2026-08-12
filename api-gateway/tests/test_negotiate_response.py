"""
What the HTTP response gives a negotiating counterparty.

The decision receipt is addressed to an auditor (DECISION_RECEIPT.md §1.1) and
reaches them through the core's structured log. None of it reaches this
response — not the hashes, not the gate, not the binding fields, and not
`version` or `canonical_prefix` either.

Trimming to those two was the first attempt and it was not enough. The prefix
is a 64-bit digest over eleven content fields, ten of which a counterparty
holds or can guess: a reviewer recovered the model's own proposed price and the
gate that fired in 7.3M SHA-256 and about eight seconds. `version` leaked
something the prefix did not — it degrades to the UNSIGNED name on any signing
failure, so watching it reported whether our transaction protein was reachable
— and `receipt: null` versus an object reported whether minting happened.

What replaces it is `dispute_token`: a random UUID minted per decision and
logged beside the receipt. Per decision, because `session_token` names a
session and a dispute is about one round of one.
"""

from unittest.mock import AsyncMock, patch

import pytest
from api_gateway.main import app
from api_gateway.security import verify_public_membrane
from aura_core_gen.aura.negotiation.v1 import NegotiateResponse, OfferCountered
from fastapi import Request
from fastapi.testclient import TestClient

TOKEN = "7c1b4a2e-0000-4000-8000-abcdefabcdef"


async def _bypass_signature(request: Request) -> str:
    """
    Stand in for the signature dependency, which is also what caches the parsed
    body. Overriding it without replacing that leaves the handler with nothing
    to read.
    """
    request.state.parsed_body = {
        "item_id": "sku-1",
        "bid_amount": 100.0,
        "currency": "USD",
        "agent_did": "did:key:test",
    }
    return "did:key:test"


@pytest.fixture
def countered_response():
    return NegotiateResponse(
        session_token="sess_abc",
        valid_until_timestamp=1,
        dispute_token=TOKEN,
        countered=OfferCountered(
            proposed_price=111.12,
            human_message="My counter-offer for this item is $111.12.",
            reason_code="NEGOTIATION_ONGOING",
        ),
    )


def _negotiate(countered_response) -> dict:
    app.dependency_overrides[verify_public_membrane] = _bypass_signature
    mock_stub = AsyncMock()
    mock_stub.negotiate.return_value = countered_response
    try:
        with patch("api_gateway.main.stub", mock_stub, create=True):
            response = TestClient(app).post(
                "/v1/negotiate",
                json={
                    "item_id": "sku-1",
                    "bid_amount": 100.0,
                    "currency": "USD",
                    "agent_did": "did:key:test",
                },
                headers={
                    "X-Agent-ID": "did:key:test",
                    "X-Timestamp": "1234567890",
                    "X-Signature": "fake-sig",
                },
            )
        assert response.status_code == 200, response.text
        return response.json()
    finally:
        app.dependency_overrides.clear()


class TestNoReceiptReachesTheCounterparty:
    def test_there_is_no_receipt_key_at_all(self, countered_response) -> None:
        assert "receipt" not in _negotiate(countered_response)

    def test_no_receipt_field_is_rendered_anywhere_in_the_body(
        self, countered_response
    ) -> None:
        """
        Against the whole serialised body, not just the top level, so a future
        renderer that nests one somewhere new fails here rather than shipping.
        """
        body = str(_negotiate(countered_response))
        for field in (
            "AURA-RECEIPT",
            "canonical_prefix",
            "claim_hash",
            "emission_hash",
            "outcome_gate",
            "override_scope",
            "ruleset_version",
            "derivation",
        ):
            assert field not in body

    def test_the_response_proto_has_no_receipt_field_left_to_render(self) -> None:
        """
        Structural, not a matter of the renderer being careful: field 7 is
        reserved on NegotiateResponse, so there is nothing to forget to trim.
        """
        assert not hasattr(NegotiateResponse(), "receipt")


class TestTheDisputeTokenIsWhatTheyCite:
    def test_it_reaches_the_client(self, countered_response) -> None:
        assert _negotiate(countered_response)["dispute_token"] == TOKEN

    def test_it_is_not_the_session_token(self, countered_response) -> None:
        """
        A dispute is about one decision. `session_token` names the session, so
        it cannot cite the third round of a negotiation — which is the reason
        this field exists rather than the session token being reused.
        """
        output = _negotiate(countered_response)
        assert output["dispute_token"] != output["session_token"]

    def test_a_decision_that_minted_nothing_carries_an_empty_token(self) -> None:
        """
        Empty rather than invented. A core that never reached the Membrane has
        no decision to cite, and a token pointing at nothing is worse than none.
        """
        bare = NegotiateResponse(session_token="sess_abc", valid_until_timestamp=1)
        assert _negotiate(bare)["dispute_token"] == ""
