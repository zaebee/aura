"""Mock tests for MistralStrategy using unittest.mock."""

from unittest.mock import MagicMock, patch

import pytest

from llm_strategy import AI_Decision, MistralStrategy


class TestMistralStrategy:
    """Test suite for MistralStrategy with mocked LLM."""

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
    def mock_session(self, mock_item):
        """Create a mock database session."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_filter = MagicMock()

        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value = mock_filter
        mock_filter.first.return_value = mock_item

        return mock_session

    @patch("llm_strategy.SessionLocal")
    @patch("llm_strategy.ChatMistralAI")
    def test_accept_response_parsing(
        self, mock_chat_mistral, mock_session_local, mock_session, mock_item
    ):
        """Test that accept response from LLM is correctly parsed."""
        # Setup mock session
        mock_session_local.return_value = mock_session

        # Setup mock LLM response
        mock_decision = AI_Decision(
            action="accept",
            price=250.0,
            message="We're happy to accept your offer!",
            reasoning="Bid is above floor price, good deal for both parties.",
        )

        mock_llm_instance = MagicMock()
        mock_structured_llm = MagicMock()
        mock_chain = MagicMock()

        mock_chat_mistral.return_value = mock_llm_instance
        mock_llm_instance.with_structured_output.return_value = mock_structured_llm
        mock_chain.invoke.return_value = mock_decision

        # Patch the chain creation to return our mock
        with patch.object(MistralStrategy, "__init__", lambda self: None):
            strategy = MistralStrategy()
            strategy.llm = mock_llm_instance
            strategy.structured_llm = mock_structured_llm

            # Mock the chain invocation via the pipe operator
            with patch("llm_strategy.ChatPromptTemplate") as mock_prompt_template:
                mock_prompt = MagicMock()
                mock_prompt_template.from_messages.return_value = mock_prompt
                mock_prompt.__or__ = MagicMock(return_value=mock_chain)

                # Mock _get_item
                strategy._get_item = MagicMock(return_value=mock_item)

                response = strategy.evaluate(
                    item_id=mock_item.id,
                    bid=250.0,
                    reputation=0.9,
                    request_id="test-req-1",
                )

        # Verify the response is correctly parsed
        assert response.HasField("accepted")
        assert response.accepted.final_price == 250.0
        assert response.accepted.reservation_code.startswith("MISTRAL-")

    @patch("llm_strategy.SessionLocal")
    @patch("llm_strategy.ChatMistralAI")
    def test_counter_response_parsing(
        self, mock_chat_mistral, mock_session_local, mock_session, mock_item
    ):
        """Test that counter response from LLM is correctly parsed."""
        mock_session_local.return_value = mock_session

        mock_decision = AI_Decision(
            action="counter",
            price=220.0,
            message="We can offer you a better deal at $220.",
            reasoning="Bid is below floor, countering with acceptable price.",
        )

        mock_llm_instance = MagicMock()
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_decision

        mock_chat_mistral.return_value = mock_llm_instance

        with patch.object(MistralStrategy, "__init__", lambda self: None):
            strategy = MistralStrategy()
            strategy.llm = mock_llm_instance
            strategy.structured_llm = MagicMock()
            strategy._get_item = MagicMock(return_value=mock_item)

            with patch("llm_strategy.ChatPromptTemplate") as mock_prompt_template:
                mock_prompt = MagicMock()
                mock_prompt_template.from_messages.return_value = mock_prompt
                mock_prompt.__or__ = MagicMock(return_value=mock_chain)

                response = strategy.evaluate(
                    item_id=mock_item.id,
                    bid=150.0,
                    reputation=0.7,
                    request_id="test-req-2",
                )

        assert response.HasField("countered")
        assert response.countered.proposed_price == 220.0
        assert response.countered.human_message == "We can offer you a better deal at $220."
        assert response.countered.reason_code == "NEGOTIATION_ONGOING"

    @patch("llm_strategy.SessionLocal")
    @patch("llm_strategy.ChatMistralAI")
    def test_reject_response_parsing(
        self, mock_chat_mistral, mock_session_local, mock_session, mock_item
    ):
        """Test that reject response from LLM is correctly parsed."""
        mock_session_local.return_value = mock_session

        mock_decision = AI_Decision(
            action="reject",
            price=0.0,
            message="We cannot accept such a low offer.",
            reasoning="Bid is insultingly low.",
        )

        mock_llm_instance = MagicMock()
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_decision

        mock_chat_mistral.return_value = mock_llm_instance

        with patch.object(MistralStrategy, "__init__", lambda self: None):
            strategy = MistralStrategy()
            strategy.llm = mock_llm_instance
            strategy.structured_llm = MagicMock()
            strategy._get_item = MagicMock(return_value=mock_item)

            with patch("llm_strategy.ChatPromptTemplate") as mock_prompt_template:
                mock_prompt = MagicMock()
                mock_prompt_template.from_messages.return_value = mock_prompt
                mock_prompt.__or__ = MagicMock(return_value=mock_chain)

                response = strategy.evaluate(
                    item_id=mock_item.id,
                    bid=1.0,
                    reputation=0.5,
                    request_id="test-req-3",
                )

        assert response.HasField("rejected")
        assert response.rejected.reason_code == "OFFER_TOO_LOW"

    @patch("llm_strategy.SessionLocal")
    @patch("llm_strategy.ChatMistralAI")
    def test_ui_required_response_parsing(
        self, mock_chat_mistral, mock_session_local, mock_session, mock_item
    ):
        """Test that ui_required response from LLM is correctly parsed."""
        mock_session_local.return_value = mock_session

        mock_decision = AI_Decision(
            action="ui_required",
            price=1500.0,
            message="This high-value transaction requires manual approval.",
            reasoning="Bid exceeds $1000 threshold, security policy triggered.",
        )

        mock_llm_instance = MagicMock()
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_decision

        mock_chat_mistral.return_value = mock_llm_instance

        with patch.object(MistralStrategy, "__init__", lambda self: None):
            strategy = MistralStrategy()
            strategy.llm = mock_llm_instance
            strategy.structured_llm = MagicMock()
            strategy._get_item = MagicMock(return_value=mock_item)

            with patch("llm_strategy.ChatPromptTemplate") as mock_prompt_template:
                mock_prompt = MagicMock()
                mock_prompt_template.from_messages.return_value = mock_prompt
                mock_prompt.__or__ = MagicMock(return_value=mock_chain)

                response = strategy.evaluate(
                    item_id=mock_item.id,
                    bid=1500.0,
                    reputation=0.9,
                    request_id="test-req-4",
                )

        assert response.HasField("ui_required")
        assert response.ui_required.template_id == "high_value_confirm"
        assert "reason" in response.ui_required.context_data

    @patch("llm_strategy.SessionLocal")
    @patch("llm_strategy.ChatMistralAI")
    def test_item_not_found(
        self, mock_chat_mistral, mock_session_local
    ):
        """Test handling of non-existent item."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_filter = MagicMock()

        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value = mock_filter
        mock_filter.first.return_value = None

        mock_session_local.return_value = mock_session

        mock_llm_instance = MagicMock()
        mock_chat_mistral.return_value = mock_llm_instance

        with patch.object(MistralStrategy, "__init__", lambda self: None):
            strategy = MistralStrategy()
            strategy.llm = mock_llm_instance
            strategy.structured_llm = MagicMock()
            strategy._get_item = MagicMock(return_value=None)

            response = strategy.evaluate(
                item_id="non-existent",
                bid=100.0,
                reputation=0.8,
                request_id="test-req-5",
            )

        assert response.HasField("rejected")
        assert response.rejected.reason_code == "ITEM_NOT_FOUND"

    @patch("llm_strategy.SessionLocal")
    @patch("llm_strategy.ChatMistralAI")
    def test_llm_error_handling(
        self, mock_chat_mistral, mock_session_local, mock_session, mock_item
    ):
        """Test that LLM errors are properly handled."""
        mock_session_local.return_value = mock_session

        mock_llm_instance = MagicMock()
        mock_chain = MagicMock()
        mock_chain.invoke.side_effect = Exception("LLM API Error")

        mock_chat_mistral.return_value = mock_llm_instance

        with patch.object(MistralStrategy, "__init__", lambda self: None):
            strategy = MistralStrategy()
            strategy.llm = mock_llm_instance
            strategy.structured_llm = MagicMock()
            strategy._get_item = MagicMock(return_value=mock_item)

            with patch("llm_strategy.ChatPromptTemplate") as mock_prompt_template:
                mock_prompt = MagicMock()
                mock_prompt_template.from_messages.return_value = mock_prompt
                mock_prompt.__or__ = MagicMock(return_value=mock_chain)

                response = strategy.evaluate(
                    item_id=mock_item.id,
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
