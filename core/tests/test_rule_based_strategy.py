"""Unit tests for RuleBasedStrategy."""

from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    ContextType,
    HiveContextData,
    NegotiationOffer,
)
from aura_core_gen.aura.core.google import protobuf
from hive.transformer.main import RuleBasedStrategy


class TestRuleBasedStrategy:
    """Test suite for RuleBasedStrategy."""

    def test_bid_below_floor_price_should_counter(self, mock_item):
        """Test case: Bid < Floor Price (Should Counter)."""
        strategy = RuleBasedStrategy()

        # Create Context
        context = Context(
            context_type=ContextType.CONTEXT_TYPE_HIVE,
            hive=HiveContextData(
                offer=NegotiationOffer(bid_amount=100.0)
            ),
            metadata=protobuf.Struct().from_dict({
                "item_name": mock_item.name,
                "floor_price": str(mock_item.floor_price),
                "base_price": str(mock_item.base_price),
            })
        )

        response = strategy.evaluate(context, request_id="test-request-1")

        # Should counter with floor price
        assert response.action == ActionType.ACTION_TYPE_COUNTER
        assert response.negotiation.price == mock_item.floor_price
        assert response.metadata.to_dict()["reason_code"] == "BELOW_FLOOR"
        assert "150" in response.negotiation.message

    def test_bid_above_trigger_price_should_ui_request(self, mock_item):
        """Test case: Bid > Trigger Price (Should UI Request)."""
        strategy = RuleBasedStrategy(trigger_price=1000.0)

        context = Context(
            context_type=ContextType.CONTEXT_TYPE_HIVE,
            hive=HiveContextData(
                offer=NegotiationOffer(bid_amount=1500.0)
            ),
            metadata=protobuf.Struct().from_dict({
                "item_name": mock_item.name,
                "floor_price": str(mock_item.floor_price),
                "base_price": str(mock_item.base_price),
            })
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
            hive=HiveContextData(
                offer=NegotiationOffer(bid_amount=150.0)
            ),
            metadata=protobuf.Struct().from_dict({
                "item_name": mock_item.name,
                "floor_price": str(mock_item.floor_price),
                "base_price": str(mock_item.base_price),
            })
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
            hive=HiveContextData(
                offer=NegotiationOffer(bid_amount=175.0)
            ),
            metadata=protobuf.Struct().from_dict({
                "item_name": mock_item.name,
                "floor_price": str(mock_item.floor_price),
                "base_price": str(mock_item.base_price),
            })
        )

        response = strategy.evaluate(context, request_id="test-request-4")

        assert response.action == ActionType.ACTION_TYPE_ACCEPT
        assert response.negotiation.price == 175.0

    def test_bid_above_base_price_should_accept(self, mock_item):
        """Test that bid above base price is accepted."""
        strategy = RuleBasedStrategy()

        context = Context(
            context_type=ContextType.CONTEXT_TYPE_HIVE,
            hive=HiveContextData(
                offer=NegotiationOffer(bid_amount=250.0)
            ),
            metadata=protobuf.Struct().from_dict({
                "item_name": mock_item.name,
                "floor_price": str(mock_item.floor_price),
                "base_price": str(mock_item.base_price),
            })
        )

        response = strategy.evaluate(context, request_id="test-request-5")

        assert response.action == ActionType.ACTION_TYPE_ACCEPT
        assert response.negotiation.price == 250.0

    def test_item_not_found_should_reject(self):
        """Test that non-existent item returns rejection."""
        strategy = RuleBasedStrategy()

        context = Context(
            context_type=ContextType.CONTEXT_TYPE_HIVE,
            hive=HiveContextData(
                offer=NegotiationOffer(bid_amount=100.0)
            ),
            metadata=protobuf.Struct().from_dict({}) # Empty metadata
        )

        response = strategy.evaluate(context, request_id="test-request-6")

        assert response.action == ActionType.ACTION_TYPE_REJECT
        assert response.metadata.to_dict()["reason_code"] == "ITEM_NOT_FOUND"
