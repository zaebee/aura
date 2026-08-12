"""Unit tests for RuleBasedStrategy."""

from aura_core_gen.aura.core.google import protobuf
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    ContextType,
    HiveContextData,
    NegotiationOffer,
)
from aura_hive.hive.transformer.main import RuleBasedStrategy


class TestRuleBasedStrategy:
    """Test suite for RuleBasedStrategy."""

    def test_bid_below_floor_price_should_counter(self, mock_item):
        """Test case: Bid < Floor Price (Should Counter)."""
        strategy = RuleBasedStrategy()

        # Create Context
        context = Context(
            context_type=ContextType.CONTEXT_TYPE_HIVE,
            hive=HiveContextData(offer=NegotiationOffer(bid_amount=100.0)),
            metadata=protobuf.Struct().from_dict(
                {
                    "item_name": mock_item.name,
                    "floor_price": str(mock_item.floor_price),
                    "base_price": str(mock_item.base_price),
                }
            ),
        )

        response = strategy.evaluate(context, request_id="test-request-1")

        # Counters, but does NOT price the counter itself. This test used to
        # assert `price == floor_price` and `"150" in message` — it pinned the
        # floor leak as the intended contract, which is why the leak survived
        # every review of this file. The guard owns floor-derived pricing; the
        # strategy proposes the bid back and the Membrane substitutes.
        assert response.action == ActionType.ACTION_TYPE_COUNTER
        assert response.negotiation.price != mock_item.floor_price
        assert response.metadata.to_dict()["reason_code"] == "BELOW_FLOOR"
        assert "150" not in response.negotiation.message

    def test_bid_above_trigger_price_should_ui_request(self, mock_item):
        """Test case: Bid > Trigger Price (Should UI Request)."""
        strategy = RuleBasedStrategy(trigger_price=1000.0)

        context = Context(
            context_type=ContextType.CONTEXT_TYPE_HIVE,
            hive=HiveContextData(offer=NegotiationOffer(bid_amount=1500.0)),
            metadata=protobuf.Struct().from_dict(
                {
                    "item_name": mock_item.name,
                    "floor_price": str(mock_item.floor_price),
                    "base_price": str(mock_item.base_price),
                }
            ),
        )

        response = strategy.evaluate(context, request_id="test-request-2")

        # Should require UI confirmation (ACTION_TYPE_EVALUATE surrogate)
        assert response.action == ActionType.ACTION_TYPE_EVALUATE
        assert response.metadata.to_dict()["template_id"] == "high_value_confirm"
        assert "1500" in response.negotiation.message

    def test_bid_at_floor_price_should_accept(self, mock_item):
        """Test that bid exactly at floor price is accepted."""
        strategy = RuleBasedStrategy()

        context = Context(
            context_type=ContextType.CONTEXT_TYPE_HIVE,
            hive=HiveContextData(offer=NegotiationOffer(bid_amount=150.0)),
            metadata=protobuf.Struct().from_dict(
                {
                    "item_name": mock_item.name,
                    "floor_price": str(mock_item.floor_price),
                    "base_price": str(mock_item.base_price),
                }
            ),
        )

        response = strategy.evaluate(context, request_id="test-request-3")

        assert response.action == ActionType.ACTION_TYPE_ACCEPT
        assert response.negotiation.price == 150.0
        assert response.metadata.to_dict()["reservation_code"].startswith("RULE-")

    def test_bid_between_floor_and_base_should_accept(self, mock_item):
        """Test that bid between floor and base price is accepted."""
        strategy = RuleBasedStrategy()

        context = Context(
            context_type=ContextType.CONTEXT_TYPE_HIVE,
            hive=HiveContextData(offer=NegotiationOffer(bid_amount=175.0)),
            metadata=protobuf.Struct().from_dict(
                {
                    "item_name": mock_item.name,
                    "floor_price": str(mock_item.floor_price),
                    "base_price": str(mock_item.base_price),
                }
            ),
        )

        response = strategy.evaluate(context, request_id="test-request-4")

        assert response.action == ActionType.ACTION_TYPE_ACCEPT
        assert response.negotiation.price == 175.0

    def test_bid_above_base_price_should_accept(self, mock_item):
        """Test that bid above base price is accepted."""
        strategy = RuleBasedStrategy()

        context = Context(
            context_type=ContextType.CONTEXT_TYPE_HIVE,
            hive=HiveContextData(offer=NegotiationOffer(bid_amount=250.0)),
            metadata=protobuf.Struct().from_dict(
                {
                    "item_name": mock_item.name,
                    "floor_price": str(mock_item.floor_price),
                    "base_price": str(mock_item.base_price),
                }
            ),
        )

        response = strategy.evaluate(context, request_id="test-request-5")

        assert response.action == ActionType.ACTION_TYPE_ACCEPT
        assert response.negotiation.price == 250.0

    def test_item_not_found_should_reject(self):
        """Test that non-existent item returns rejection."""
        strategy = RuleBasedStrategy()

        context = Context(
            context_type=ContextType.CONTEXT_TYPE_HIVE,
            hive=HiveContextData(offer=NegotiationOffer(bid_amount=100.0)),
            metadata=protobuf.Struct().from_dict({}),  # Empty metadata
        )

        response = strategy.evaluate(context, request_id="test-request-6")

        assert response.action == ActionType.ACTION_TYPE_REJECT
        assert response.metadata.to_dict()["reason_code"] == "ITEM_NOT_FOUND"


class TestTheFloorDoesNotLeaveInRulesMode:
    """
    The rules strategy countered at the floor exactly, and said so in prose.

    `DECISION_RECEIPT.md` §3.4 bounds what a counterparty learns about the
    floor at 3% — the markup and per-session jitter the guard applies to every
    floor-derived price. This path bypassed both: `price=floor_price` is a 0%
    bound, and `"We cannot accept less than $1000.0."` states the number
    outright. The Membrane's DLP scans for the literal token `floor_price`, not
    for its value, so nothing downstream caught it.

    Two leaks, one cause: this strategy priced from the floor itself instead of
    asking the component that owns floor-derived pricing.
    """

    FLOOR = 1000.0

    def _context(self, bid: float) -> Context:
        return Context(
            context_type=ContextType.CONTEXT_TYPE_HIVE,
            hive=HiveContextData(offer=NegotiationOffer(bid_amount=bid)),
            metadata=protobuf.Struct().from_dict(
                {"item_name": "room", "floor_price": str(self.FLOOR)}
            ),
        )

    def test_the_counter_is_not_the_floor_itself(self) -> None:
        strategy = RuleBasedStrategy()

        response = strategy.evaluate(self._context(bid=100.0))

        assert response.action == ActionType.ACTION_TYPE_COUNTER
        assert response.negotiation.price != self.FLOOR

    def test_the_message_does_not_state_the_floor(self) -> None:
        strategy = RuleBasedStrategy()

        message = strategy.evaluate(self._context(bid=100.0)).negotiation.message

        assert "1000" not in message, message
