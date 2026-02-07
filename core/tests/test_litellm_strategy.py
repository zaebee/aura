from unittest.mock import patch

from src.hive.proteins.reasoning.enzymes.reasoning_engine import (
    AI_Decision,
    LiteLLMStrategy,
)


class TestLiteLLMStrategy:
    def test_evaluate_item_not_found(self):
        strategy = LiteLLMStrategy(model="gpt-3.5-turbo")
        response = strategy.evaluate(item=None, bid=100.0, reputation=0.8)
        assert response.rejected.reason_code == "ITEM_NOT_FOUND"

    @patch("src.hive.proteins.reasoning.enzymes.reasoning_engine.LLMEngine")
    def test_evaluate_accept(self, mock_engine_class, mock_item):
        mock_engine = mock_engine_class.return_value
        mock_engine.complete.return_value = AI_Decision(
            action="accept",
            price=150.0,
            message="We accept your offer.",
            reasoning="Bid meets our requirements.",
        )

        with (
            patch("src.hive.proteins.reasoning.enzymes.reasoning_engine.Template"),
            patch(
                "src.hive.proteins.reasoning.enzymes.reasoning_engine.open", create=True
            ),
        ):
            strategy = LiteLLMStrategy(model="gpt-3.5-turbo")
            response = strategy.evaluate(item=mock_item, bid=150.0, reputation=0.8)

            assert response.accepted.final_price == 150.0
            assert "LLM-" in response.accepted.reservation_code

    @patch("src.hive.proteins.reasoning.enzymes.reasoning_engine.LLMEngine")
    def test_evaluate_counter(self, mock_engine_class, mock_item):
        mock_engine = mock_engine_class.return_value
        mock_engine.complete.return_value = AI_Decision(
            action="counter",
            price=180.0,
            message="Can you do 180?",
            reasoning="Bid is a bit low.",
        )

        with (
            patch("src.hive.proteins.reasoning.enzymes.reasoning_engine.Template"),
            patch(
                "src.hive.proteins.reasoning.enzymes.reasoning_engine.open", create=True
            ),
        ):
            strategy = LiteLLMStrategy(model="gpt-3.5-turbo")
            response = strategy.evaluate(item=mock_item, bid=150.0, reputation=0.8)

            assert response.countered.proposed_price == 180.0
            assert response.countered.human_message == "Can you do 180?"

    @patch("src.hive.proteins.reasoning.enzymes.reasoning_engine.LLMEngine")
    def test_evaluate_reject(self, mock_engine_class, mock_item):
        mock_engine = mock_engine_class.return_value
        mock_engine.complete.return_value = AI_Decision(
            action="reject", price=0.0, message="No thanks.", reasoning="Way too low."
        )

        with (
            patch("src.hive.proteins.reasoning.enzymes.reasoning_engine.Template"),
            patch(
                "src.hive.proteins.reasoning.enzymes.reasoning_engine.open", create=True
            ),
        ):
            strategy = LiteLLMStrategy(model="gpt-3.5-turbo")
            response = strategy.evaluate(item=mock_item, bid=50.0, reputation=0.8)

            assert response.rejected.reason_code == "OFFER_TOO_LOW"

    @patch("src.hive.proteins.reasoning.enzymes.reasoning_engine.LLMEngine")
    def test_evaluate_ai_error(self, mock_engine_class, mock_item):
        mock_engine = mock_engine_class.return_value
        mock_engine.complete.side_effect = Exception("API error")

        with (
            patch("src.hive.proteins.reasoning.enzymes.reasoning_engine.Template"),
            patch(
                "src.hive.proteins.reasoning.enzymes.reasoning_engine.open", create=True
            ),
        ):
            strategy = LiteLLMStrategy(model="gpt-3.5-turbo")
            response = strategy.evaluate(item=mock_item, bid=150.0, reputation=0.8)

            assert response.rejected.reason_code == "AI_ERROR"
