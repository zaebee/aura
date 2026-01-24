"""Unit tests for RuleBasedStrategy."""


from llm_strategy import RuleBasedStrategy


class TestRuleBasedStrategy:
    """Test suite for RuleBasedStrategy."""

    def test_bid_below_floor_price_should_counter(self, mock_repository, mock_item):
        """Test case: Bid < Floor Price (Should Counter).

        When a bid is below the floor price, the strategy should
        return a counter offer with the floor price.
        """
        strategy = RuleBasedStrategy(repository=mock_repository)

        # Bid below floor price (floor_price=150)
        response = strategy.evaluate(
            item_id=mock_item.id,
            bid=100.0,
            reputation=0.8,
            request_id="test-request-1",
        )

        # Should counter with floor price
        assert response.HasField("countered")
        assert response.countered.proposed_price == mock_item.floor_price
        assert response.countered.reason_code == "BELOW_FLOOR"
        assert "150" in response.countered.human_message

    def test_bid_above_trigger_price_should_ui_request(
        self, mock_repository, mock_item
    ):
        """Test case: Bid > Trigger Price (Should UI Request).

        When a bid exceeds the trigger price (security threshold),
        the strategy should return a UI required response.
        """
        strategy = RuleBasedStrategy(repository=mock_repository, trigger_price=1000.0)

        # Bid above trigger price
        response = strategy.evaluate(
            item_id=mock_item.id,
            bid=1500.0,
            reputation=0.9,
            request_id="test-request-2",
        )

        # Should require UI confirmation
        assert response.HasField("ui_required")
        assert response.ui_required.template_id == "high_value_confirm"
        assert "1500" in response.ui_required.context_data["reason"]

    def test_bid_at_floor_price_should_accept(self, mock_repository, mock_item):
        """Test that bid exactly at floor price is accepted."""
        strategy = RuleBasedStrategy(repository=mock_repository)

        response = strategy.evaluate(
            item_id=mock_item.id,
            bid=150.0,  # Exactly at floor price
            reputation=0.8,
            request_id="test-request-3",
        )

        assert response.HasField("accepted")
        assert response.accepted.final_price == 150.0
        assert response.accepted.reservation_code.startswith("RULE-")

    def test_bid_between_floor_and_base_should_accept(
        self, mock_repository, mock_item
    ):
        """Test that bid between floor and base price is accepted."""
        strategy = RuleBasedStrategy(repository=mock_repository)

        response = strategy.evaluate(
            item_id=mock_item.id,
            bid=175.0,  # Between floor (150) and base (200)
            reputation=0.8,
            request_id="test-request-4",
        )

        assert response.HasField("accepted")
        assert response.accepted.final_price == 175.0

    def test_bid_above_base_price_should_accept(self, mock_repository, mock_item):
        """Test that bid above base price is accepted."""
        strategy = RuleBasedStrategy(repository=mock_repository)

        response = strategy.evaluate(
            item_id=mock_item.id,
            bid=250.0,  # Above base price (200)
            reputation=0.8,
            request_id="test-request-5",
        )

        assert response.HasField("accepted")
        assert response.accepted.final_price == 250.0

    def test_item_not_found_should_reject(self, mock_repository):
        """Test that non-existent item returns rejection."""
        strategy = RuleBasedStrategy(repository=mock_repository)

        response = strategy.evaluate(
            item_id="non-existent-item",
            bid=100.0,
            reputation=0.8,
            request_id="test-request-6",
        )

        assert response.HasField("rejected")
        assert response.rejected.reason_code == "ITEM_NOT_FOUND"

    def test_custom_trigger_price(self, mock_repository, mock_item):
        """Test that custom trigger price is respected."""
        # Set a lower trigger price
        strategy = RuleBasedStrategy(repository=mock_repository, trigger_price=500.0)

        response = strategy.evaluate(
            item_id=mock_item.id,
            bid=600.0,  # Above custom trigger (500)
            reputation=0.8,
            request_id="test-request-7",
        )

        assert response.HasField("ui_required")

    def test_bid_just_below_trigger_should_accept(self, mock_repository, mock_item):
        """Test that bid just below trigger price is accepted."""
        strategy = RuleBasedStrategy(repository=mock_repository, trigger_price=1000.0)

        response = strategy.evaluate(
            item_id=mock_item.id,
            bid=999.0,  # Just below trigger
            reputation=0.8,
            request_id="test-request-8",
        )

        assert response.HasField("accepted")
        assert response.accepted.final_price == 999.0

    def test_bid_exactly_at_trigger_should_accept(self, mock_repository, mock_item):
        """Test that bid exactly at trigger price is accepted (not > trigger)."""
        strategy = RuleBasedStrategy(repository=mock_repository, trigger_price=1000.0)

        response = strategy.evaluate(
            item_id=mock_item.id,
            bid=1000.0,  # Exactly at trigger
            reputation=0.8,
            request_id="test-request-9",
        )

        # Should accept because condition is bid > trigger_price, not >=
        assert response.HasField("accepted")
        assert response.accepted.final_price == 1000.0
