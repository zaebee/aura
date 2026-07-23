"""Unit tests for MCPTranslator — the pure Signal/Observation transforms."""

from aura_core_gen.aura.core.v1 import (
    NegotiationObservation,
    Observation,
    OfferAccepted,
    OfferCountered,
    OfferRejected,
    SignalType,
)

from translator import MCPTranslator


def _struct_to_dict(struct):
    return struct.to_dict() if hasattr(struct, "to_dict") else dict(struct)


# --- to_signal -------------------------------------------------------------


def test_to_signal_negotiate_builds_negotiation_signal():
    sig = MCPTranslator().to_signal("negotiate", item_id="hotel-42", bid=99.5)
    assert sig.signal_type == SignalType.SIGNAL_TYPE_NEGOTIATION
    assert sig.negotiation.item_identifier == "hotel-42"
    assert sig.negotiation.bid_amount == 99.5
    assert sig.negotiation.agent.did == "mcp-agent"
    assert sig.identifier  # a uuid was assigned


def test_to_signal_search_encodes_query_metadata():
    sig = MCPTranslator().to_signal("search", query="beach hotels", limit=5)
    assert sig.signal_type == SignalType.SIGNAL_TYPE_UNSPECIFIED
    meta = _struct_to_dict(sig.metadata)
    assert meta["query"] == "beach hotels"
    assert meta["limit"] == "5"
    assert meta["intent"] == "search"


def test_to_signal_unknown_tool_returns_unspecified():
    sig = MCPTranslator().to_signal("frobnicate")
    assert sig.signal_type == SignalType.SIGNAL_TYPE_UNSPECIFIED
    assert sig.identifier


# --- from_observation ------------------------------------------------------


def test_from_observation_failure_reports_error():
    obs = Observation(success=False, error="boom")
    assert MCPTranslator().from_observation(obs) == "❌ Operation failed: boom"


def test_from_observation_success_without_negotiation():
    obs = Observation(success=True)
    assert "no negotiation data" in MCPTranslator().from_observation(obs)


def test_from_observation_accepted():
    obs = Observation(
        success=True,
        negotiation=NegotiationObservation(accepted=OfferAccepted(final_price=123.45)),
    )
    assert (
        MCPTranslator().from_observation(obs)
        == "🎉 SUCCESS! Negotiation accepted at $123.45."
    )


def test_from_observation_countered():
    obs = Observation(
        success=True,
        negotiation=NegotiationObservation(
            countered=OfferCountered(proposed_price=80.0, human_message="too low")
        ),
    )
    result = MCPTranslator().from_observation(obs)
    assert "COUNTER-OFFER: $80.00" in result
    assert "too low" in result


def test_from_observation_rejected():
    obs = Observation(
        success=True,
        negotiation=NegotiationObservation(
            rejected=OfferRejected(reason_code="NO_INVENTORY")
        ),
    )
    assert MCPTranslator().from_observation(obs) == "🚫 REJECTED. Reason: NO_INVENTORY"
