"""Unit tests for RuleBasedStrategy."""

from hive.transformer._internal import RuleBasedStrategy


class TestRuleBasedStrategy:
    """Test suite for RuleBasedStrategy."""

    def test_bid_below_floor_price_should_counter(self, mock_item):
        """Test case: Bid < Floor Price (Should Counter).

        When a bid is below the floor price, the strategy should
        return a counter offer with the floor price.
        """
        strategy = RuleBasedStrategy()

        # Bid below floor price (floor_price=150)
        response = strategy.evaluate(
            item_data={
                "floor_price": mock_item.floor_price,
                "base_price": mock_item.base_price,
            },
            bid=100.0,
            reputation=0.8,
            request_id="test-request-1",
        )

        # Should counter with floor price
        assert response.action == "counter"
        assert response.price == mock_item.floor_price
        assert response.metadata["reason_code"] == "BELOW_FLOOR"
        assert "150" in response.message

    def test_bid_above_trigger_price_should_ui_request(self, mock_item):
        """Test case: Bid > Trigger Price (Should UI Request).

        When a bid exceeds the trigger price (security threshold),
        the strategy should return a UI required response.
        """
        strategy = RuleBasedStrategy(trigger_price=1000.0)

        # Bid above trigger price
        response = strategy.evaluate(
            item_data={
                "floor_price": mock_item.floor_price,
                "base_price": mock_item.base_price,
            },
            bid=1500.0,
            reputation=0.9,
            request_id="test-request-2",
        )

        # Should require UI confirmation
        assert response.action == "ui_required"
        assert response.metadata["template_id"] == "high_value_confirm"
        assert "1500" in response.message

    def test_bid_at_floor_price_should_accept(self, mock_item):
        """Test that bid exactly at floor price is accepted."""
        strategy = RuleBasedStrategy()

        response = strategy.evaluate(
            item_data={
                "floor_price": mock_item.floor_price,
                "base_price": mock_item.base_price,
            },
            bid=150.0,  # Exactly at floor price
            reputation=0.8,
            request_id="test-request-3",
        )

        assert response.action == "accept"
        assert response.price == 150.0
        assert response.metadata["reservation_code"].startswith("RULE-")

    def test_bid_between_floor_and_base_should_accept(self, mock_item):
        """Test that bid between floor and base price is accepted."""
        strategy = RuleBasedStrategy()

        response = strategy.evaluate(
            item_data={
                "floor_price": mock_item.floor_price,
                "base_price": mock_item.base_price,
            },
            bid=175.0,  # Between floor (150) and base (200)
            reputation=0.8,
            request_id="test-request-4",
        )

        assert response.action == "accept"
        assert response.price == 175.0

    def test_bid_above_base_price_should_accept(self, mock_item):
        """Test that bid above base price is accepted."""
        strategy = RuleBasedStrategy()

        response = strategy.evaluate(
            item_data={
                "floor_price": mock_item.floor_price,
                "base_price": mock_item.base_price,
            },
            bid=250.0,  # Above base price (200)
            reputation=0.8,
            request_id="test-request-5",
        )

        assert response.action == "accept"
        assert response.price == 250.0

    def test_item_not_found_should_reject(self):
        """Test that non-existent item returns rejection."""
        strategy = RuleBasedStrategy()

        response = strategy.evaluate(
            item_data={},
            bid=100.0,
            reputation=0.8,
            request_id="test-request-6",
        )

        assert response.action == "reject"
        assert response.metadata["reason_code"] == "ITEM_NOT_FOUND"

    def test_custom_trigger_price(self, mock_item):
        """Test that custom trigger price is respected."""
        # Set a lower trigger price
        strategy = RuleBasedStrategy(trigger_price=500.0)

        response = strategy.evaluate(
            item_data={
                "floor_price": mock_item.floor_price,
                "base_price": mock_item.base_price,
            },
            bid=600.0,  # Above custom trigger (500)
            reputation=0.8,
            request_id="test-request-7",
        )

        assert response.action == "ui_required"

    def test_bid_just_below_trigger_should_accept(self, mock_item):
        """Test that bid just below trigger price is accepted."""
        strategy = RuleBasedStrategy(trigger_price=1000.0)

        response = strategy.evaluate(
            item_data={
                "floor_price": mock_item.floor_price,
                "base_price": mock_item.base_price,
            },
            bid=999.0,  # Just below trigger
            reputation=0.8,
            request_id="test-request-8",
        )

        assert response.action == "accept"
        assert response.price == 999.0

    def test_bid_exactly_at_trigger_should_accept(self, mock_item):
        """Test that bid exactly at trigger price is accepted (not > trigger)."""
        strategy = RuleBasedStrategy(trigger_price=1000.0)

        response = strategy.evaluate(
            item_data={
                "floor_price": mock_item.floor_price,
                "base_price": mock_item.base_price,
            },
            bid=1000.0,  # Exactly at trigger
            reputation=0.8,
            request_id="test-request-9",
        )

        # Should accept because condition is bid > trigger_price, not >=
        assert response.action == "accept"
        assert response.price == 1000.0
