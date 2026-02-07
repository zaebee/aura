import json
import re
from typing import Any, cast

import dspy
import structlog
from aura_core import resolve_brain_path
from langchain_mistralai import MistralAIEmbeddings

logger = structlog.get_logger(__name__)

# --- JSON Cleaning Implementation ---


def clean_and_parse_json(text: str) -> dict[str, Any]:
    if not text:
        raise ValueError("Empty or null input")
    try:
        return cast(dict[str, Any], json.loads(text))
    except (json.JSONDecodeError, TypeError):
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            try:
                return cast(dict[str, Any], json.loads(match.group(1)))
            except json.JSONDecodeError:
                pass
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            try:
                return cast(dict[str, Any], json.loads(text[start : end + 1]))
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Could not parse JSON from: {text[:100]}...") from None


# --- DSPy Signatures and Modules ---


class Negotiate(dspy.Signature):
    """Negotiation decision signature."""

    input_bid = dspy.InputField(desc="Current buyer bid")
    context = dspy.InputField(desc="Economic context JSON")
    history = dspy.InputField(desc="Negotiation history JSON")
    thought = dspy.OutputField(desc="Strategic reasoning")
    action = dspy.OutputField(desc="Decision JSON with action, price, message")


class AuraNegotiator(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.negotiate = dspy.Predict(Negotiate)

    def forward(
        self, input_bid: float, context: Any, history: Any = None
    ) -> dict[str, Any]:
        h_json = history if isinstance(history, str) else json.dumps(history or [])
        c_json = context if isinstance(context, str) else json.dumps(context)
        pred = self.negotiate(input_bid=str(input_bid), context=c_json, history=h_json)
        try:
            action_data = clean_and_parse_json(pred.action)
            return cast(
                dict[str, Any],
                {
                    "thought": pred.thought,
                    "action": action_data,
                    "raw_action": pred.action,
                },
            )
        except Exception as e:
            raise ValueError(f"Negotiator parsing failed: {e}") from e


# --- Embeddings Implementation ---


def get_embedding_model(api_key: str) -> MistralAIEmbeddings:
    return MistralAIEmbeddings(
        model="mistral-embed",
        mistral_api_key=api_key,
    )


def generate_embedding(text: str, model: MistralAIEmbeddings) -> list[float]:
    return cast(list[float], model.embed_query(text))


# --- Brain Loading Helper ---


def load_brain(compiled_path: str | None = None) -> Any:
    """Load the DSPy brain using the standardized absolute discovery logic."""
    path = resolve_brain_path(compiled_path)
    if path != "UNKNOWN":
        try:
            return dspy.load(path)
        except Exception:  # nosec B112
            logger.warning("failed_to_load_brain", path=path)

    return AuraNegotiator()
