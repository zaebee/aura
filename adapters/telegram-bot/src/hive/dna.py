from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from aiogram.types import InlineKeyboardMarkup
from aura_core.dna import (
    Event as Event,
)
from aura_core.dna import (
    HiveContext as HiveContext,
)
from aura_core.dna import (
    NegotiationOffer as NegotiationOffer,
)
from aura_core.dna import (
    NegotiationResult as NegotiationResult,
)
from aura_core.dna import (
    Observation as Observation,
)
from aura_core.dna import (
    SearchResult as SearchResult,
)


@dataclass
class TelegramContext:
    """Context specific to Telegram interactions."""

    user_id: int
    chat_id: int
    hive_context: HiveContext | None = None
    message_text: str | None = None
    callback_data: str | None = None
    fsm_state: str | None = None
    fsm_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class UIAction:
    """Structured action for the Telegram UI."""

    text: str
    reply_markup: InlineKeyboardMarkup | None = None
    parse_mode: str | None = "Markdown"
    action_type: str = (
        "send_message"  # e.g., "send_message", "answer_callback", "edit_message"
    )
    show_thinking: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


# Specialized Protocols for Telegram if needed, otherwise use the core ones
@runtime_checkable
class TelegramAggregator(Protocol):
    """A - Aggregator: Extracts Telegram signals into context."""

    async def perceive(
        self, signal: Any, state_data: dict[str, Any]
    ) -> TelegramContext: ...


@runtime_checkable
class TelegramTransformer(Protocol):
    """T - Transformer: Decides on UI actions."""

    async def think(
        self,
        context: TelegramContext,
        core_response: NegotiationResult | None = None,
        search_results: list[SearchResult] | None = None,
    ) -> UIAction: ...


@runtime_checkable
class TelegramConnector(Protocol):
    """C - Connector: Executes UI actions and gRPC calls."""

    async def act(self, action: UIAction, context: TelegramContext) -> Observation: ...

    async def call_core(self, context: TelegramContext) -> NegotiationResult: ...

    async def search_core(self, query: str) -> list[SearchResult]: ...


@runtime_checkable
class TelegramGenerator(Protocol):
    """G - Generator: Emits events to NATS."""

    async def pulse(self, observation: Observation) -> list[Event]: ...
