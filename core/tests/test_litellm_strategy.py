"""Mock tests for LiteLLMStrategy using unittest.mock."""

from unittest.mock import MagicMock, patch

import pytest
from src.hive.proteins.reasoning._internal import AI_Decision, LiteLLMStrategy


class TestLiteLLMStrategy:
    """Test suite for LiteLLMStrategy with mocked LLM."""

    @pytest.fixture
    def mock_item(self):
        """Create a mock inventory item."""
        item = MagicMock()
        item.id = "room-202"
        item.name = "Premium Suite"
        item.base_price = 300.0
        item.floor_price = 200.0
        item.is_active = True
        item.meta = {}
        return item

    @pytest.fixture
    def mock_strategy(self, mock_item):
        """Create a LiteLLMStrategy with mocked dependencies."""
        # Use a mock Template to avoid loading the real file
        with (
            patch("src.hive.proteins.reasoning._internal.Template"),
            patch("builtins.open"),
        ):
            strategy = LiteLLMStrategy(model="openai/gpt-4o", temperature=0.7)
            return strategy

    def test_accept_response_parsing(self, mock_strategy, mock_item):
        mock_strategy.prompt_template = MagicMock()
        """Test that accept response from LLM is correctly parsed."""
        decision = AI_Decision(
            action="accept",
            price=250.0,
            message="We're happy to accept your offer!",
            reasoning="Bid is above floor price, good deal for both parties.",
        )

        with patch.object(mock_strategy.engine, "complete", return_value=decision):
            response = mock_strategy.evaluate(
                item=mock_item,
                bid=250.0,
                reputation=0.8,
                request_id="test-req-1",
            )

        assert response.HasField("accepted")
        assert response.accepted.final_price == 250.0
        assert response.accepted.reservation_code.startswith("LLM-")

    def test_counter_response_parsing(self, mock_strategy, mock_item):
        mock_strategy.prompt_template = MagicMock()
        """Test that counter response from LLM is correctly parsed."""
        decision = AI_Decision(
            action="counter",
            price=220.0,
            message="We can offer you a better deal at $220.",
            reasoning="Bid is below floor, countering with acceptable price.",
        )

        with patch.object(mock_strategy.engine, "complete", return_value=decision):
            response = mock_strategy.evaluate(
                item=mock_item,
                bid=150.0,
                reputation=0.8,
                request_id="test-req-2",
            )

        assert response.HasField("countered")
        assert response.countered.proposed_price == 220.0
        assert (
            response.countered.human_message
            == "We can offer you a better deal at $220."
        )
        assert response.countered.reason_code == "NEGOTIATION_ONGOING"

    def test_reject_response_parsing(self, mock_strategy, mock_item):
        mock_strategy.prompt_template = MagicMock()
        """Test that reject response from LLM is correctly parsed."""
        decision = AI_Decision(
            action="reject",
            price=0.0,
            message="We cannot accept such a low offer.",
            reasoning="Bid is insultingly low.",
        )

        with patch.object(mock_strategy.engine, "complete", return_value=decision):
            response = mock_strategy.evaluate(
                item=mock_item,
                bid=1.0,
                reputation=0.8,
                request_id="test-req-3",
            )

        assert response.HasField("rejected")
        assert response.rejected.reason_code == "OFFER_TOO_LOW"

    def test_ui_required_response_parsing(self, mock_strategy, mock_item):
        mock_strategy.prompt_template = MagicMock()
        """Test that ui_required response from LLM is correctly parsed."""
        decision = AI_Decision(
            action="ui_required",
            price=1500.0,
            message="This high-value transaction requires manual approval.",
            reasoning="Bid exceeds $1000 threshold, security policy triggered.",
        )

        with patch.object(mock_strategy.engine, "complete", return_value=decision):
            response = mock_strategy.evaluate(
                item=mock_item,
                bid=1500.0,
                reputation=0.8,
                request_id="test-req-4",
            )

        assert response.HasField("ui_required")
        assert response.ui_required.template_id == "high_value_confirm"
        assert "reason" in response.ui_required.context_data

    def test_item_not_found(self, mock_strategy):
        """Test handling of non-existent item."""
        response = mock_strategy.evaluate(
            item=None,
            bid=100.0,
            reputation=0.8,
            request_id="test-req-5",
        )

        assert response.HasField("rejected")
        assert response.rejected.reason_code == "ITEM_NOT_FOUND"

    def test_llm_error_handling(self, mock_strategy, mock_item):
        mock_strategy.prompt_template = MagicMock()
        """Test that LLM errors are properly handled."""
        with patch.object(
            mock_strategy.engine, "complete", side_effect=Exception("LLM API Error")
        ):
            response = mock_strategy.evaluate(
                item=mock_item,
                bid=200.0,
                reputation=0.8,
                request_id="test-req-6",
            )

        assert response.HasField("rejected")
        assert response.rejected.reason_code == "AI_ERROR"


class TestAIDecisionModel:
    """Test the AI_Decision Pydantic model."""

    def test_valid_decision_creation(self):
        """Test creating a valid AI_Decision."""
        decision = AI_Decision(
            action="accept",
            price=250.0,
            message="Deal accepted!",
            reasoning="Good price.",
        )

        assert decision.action == "accept"
        assert decision.price == 250.0
        assert decision.message == "Deal accepted!"
        assert decision.reasoning == "Good price."

    def test_decision_with_all_actions(self):
        """Test that all valid actions can be used."""
        actions = ["accept", "counter", "reject", "ui_required"]

        for action in actions:
            decision = AI_Decision(
                action=action,
                price=100.0,
                message="Test message",
                reasoning="Test reasoning",
            )
            assert decision.action == action
