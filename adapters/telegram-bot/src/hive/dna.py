from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable, Optional, List
from aiogram.types import InlineKeyboardMarkup


@dataclass
class NegotiationOffer:
    """Internal representation of an incoming bid."""
    bid_amount: float
    reputation: float = 1.0
    agent_did: str = "telegram-user"


@dataclass
class HiveContext:
    """Consolidated context for the Hive's decision making."""
    item_id: str
    offer: NegotiationOffer
    item_data: dict[str, Any] = field(default_factory=dict)
    system_health: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TelegramContext:
    """Context specific to Telegram interactions."""
    user_id: int
    chat_id: int
    hive_context: Optional[HiveContext] = None
    message_text: Optional[str] = None
    callback_data: Optional[str] = None
    fsm_state: Optional[str] = None
    fsm_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class UIAction:
    """Structured action for the Telegram UI."""
    text: str
    reply_markup: Optional[InlineKeyboardMarkup] = None
    parse_mode: Optional[str] = "Markdown"
    action_type: str = "send_message"  # e.g., "send_message", "answer_callback", "edit_message"
    show_thinking: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Observation:
    """Observation resulting from an action."""
    success: bool
    message_id: Optional[int] = None
    error: Optional[str] = None
    event_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    """An event emitted to the Hive's blood stream (NATS)."""
    topic: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=lambda: 0.0)


@runtime_checkable
class BeeDNA(Protocol):
    """Protocol for the Telegram Bot Hive components."""
    pass


@runtime_checkable
class Aggregator(Protocol):
    """A - Aggregator: Extracts Telegram signals into context."""
    async def perceive(self, signal: Any, state_data: dict[str, Any]) -> TelegramContext:
        ...


@runtime_checkable
class Transformer(Protocol):
    """T - Transformer: Decides on UI actions."""
    async def think(self, context: TelegramContext, core_response: Optional[dict[str, Any]] = None, search_results: Optional[List[dict[str, Any]]] = None) -> UIAction:
        ...


@runtime_checkable
class Connector(Protocol):
    """C - Connector: Executes UI actions and gRPC calls."""
    async def act(self, action: UIAction, context: TelegramContext) -> Observation:
        ...

    async def call_core(self, context: TelegramContext) -> dict[str, Any]:
        ...


@runtime_checkable
class Generator(Protocol):
    """G - Generator: Emits events to NATS."""
    async def pulse(self, observation: Observation) -> list[Event]:
        ...
