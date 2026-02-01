from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "NegotiationOffer",
    "HiveContext",
    "IntentAction",
    "FailureIntent",
    "Observation",
    "Event",
    "BeeContext",
    "PurityReport",
    "BeeObservation",
    "TelegramContext",
    "UIAction",
]


@dataclass
class NegotiationOffer:
    """Internal representation of an incoming bid."""

    bid_amount: float
    reputation: float = 1.0
    agent_did: str = ""


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
class IntentAction:
    """Strictly typed intent returned by the Transformer."""

    action: str  # "accept", "counter", "reject", "ui_required"
    price: float
    message: str
    thought: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FailureIntent(IntentAction):
    """Specialized intent for when the LLM or processing fails."""

    error: str = ""
    action: str = "error"
    price: float = 0.0
    message: str = "Internal processing error. Defaulting to safe state."


@dataclass
class Observation:
    """Observation resulting from an action."""

    success: bool
    data: Any = None
    event_type: str = ""
    message_id: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    """An event emitted to the Hive's blood stream (NATS)."""

    topic: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=lambda: 0.0)


# BeeKeeper specific types
@dataclass
class BeeContext:
    """Consolidated context for the BeeKeeper's audit."""
    git_diff: str
    hive_metrics: dict[str, Any]
    filesystem_map: list[str]
    repo_name: str
    event_name: str = "manual"
    event_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PurityReport:
    """The raw result of an architectural audit."""
    is_pure: bool
    heresies: list[str] = field(default_factory=list)
    narrative: str = ""
    reasoning: str = ""
    execution_time: float = 0.0
    token_usage: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BeeObservation:
    """Observation resulting from BeeKeeper's actions."""
    success: bool
    github_comment_url: str = ""
    nats_event_sent: bool = False
    injuries: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# Telegram Bot specific types
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
    reply_markup: Any = None  # InlineKeyboardMarkup
    parse_mode: str | None = "Markdown"
    action_type: str = (
        "send_message"  # e.g., "send_message", "answer_callback", "edit_message"
    )
    show_thinking: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
