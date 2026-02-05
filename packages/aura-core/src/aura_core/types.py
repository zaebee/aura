import time
from dataclasses import dataclass, field
from typing import Any, Protocol, TypedDict, cast, runtime_checkable

from pydantic import BaseModel, SecretStr

from .gen.aura.dna.v1 import ActionType


def map_action(action_str: str | None) -> ActionType:
    """
    Standardized mapper for negotiation actions.
    Converts LLM strings to strict ActionType enum.
    """
    from typing import cast

    if not action_str:
        return cast(ActionType, ActionType.ACTION_TYPE_UNSPECIFIED)

    mapping = {
        "accept": ActionType.ACTION_TYPE_ACCEPT,
        "counter": ActionType.ACTION_TYPE_COUNTER,
        "counteroffer": ActionType.ACTION_TYPE_COUNTER,
        "reject": ActionType.ACTION_TYPE_REJECT,
        "ui_required": ActionType.ACTION_TYPE_UI_REQUIRED,
        "error": ActionType.ACTION_TYPE_ERROR,
    }
    val = mapping.get(action_str.lower(), ActionType.ACTION_TYPE_UNSPECIFIED)
    return cast(ActionType, val)


def get_raw_key(key_field: SecretStr | str) -> str:
    """
    Safely retrieve the raw string value from a SecretStr or a plain string.
    Fixes AttributeError: 'str' object has no attribute 'get_secret_value'.
    """
    if isinstance(key_field, SecretStr):
        return key_field.get_secret_value()
    return key_field  # It's already a string


@runtime_checkable
class Signal(Protocol):
    """Protocol for inbound signals."""

    pass


class SystemVitals(BaseModel):
    """Standardized system health metrics."""

    status: str
    cpu_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    timestamp: str = ""
    cached: bool = False
    warnings: list[str] = []
    error: str | None = None


@dataclass
class NegotiationOffer:
    """Internal representation of an incoming bid."""

    bid_amount: float
    reputation: float = 1.0
    agent_did: str = "unknown"


@dataclass
class HiveContext:
    """Consolidated context for the Hive's decision making."""

    item_id: str
    offer: NegotiationOffer
    item_data: dict[str, Any] = field(default_factory=dict)
    system_health: SystemVitals | dict[str, Any] = field(default_factory=dict)
    request_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IntentAction:
    """Strictly typed intent returned by the Transformer."""

    action: str | ActionType  # String for legacy, ActionType for crystalline
    price: float
    message: str
    thought: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FailureIntent(IntentAction):
    """Specialized intent for when the LLM or processing fails."""

    error: str = ""
    action: str | ActionType = cast(ActionType, ActionType.ACTION_TYPE_ERROR)
    price: float = 0.0
    message: str = "Internal processing error. Defaulting to safe state."


@dataclass
class Observation:
    """Observation resulting from an action."""

    success: bool
    data: Any = None
    message_id: int | None = None
    error: str | None = None
    event_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    """An event emitted to the Hive's blood stream (NATS)."""

    topic: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class SearchResult(TypedDict):
    item_id: str
    name: str
    base_price: float
    description_snippet: str | None


class NegotiationResult(TypedDict, total=False):
    accepted: dict[str, Any] | None
    countered: dict[str, Any] | None
    rejected: dict[str, Any] | None
    ui_required: dict[str, Any] | None
    error: str | None


@dataclass
class BeeContext:
    """Consolidated context for the BeeKeeper's audit."""

    git_diff: str
    hive_metrics: dict[str, Any]
    filesystem_map: list[str]
    repo_name: str
    system_health: SystemVitals | dict[str, Any] = field(default_factory=dict)
    event_name: str = "manual"
    event_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditObservation:
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
    report: "AuditObservation | None" = None
    context: "BeeContext | None" = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TelegramContext:
    """Context specific to Telegram interactions."""

    user_id: int
    chat_id: int
    hive_context: HiveContext | None = None
    system_health: SystemVitals | dict[str, Any] = field(default_factory=dict)
    message_text: str | None = None
    callback_data: str | None = None
    fsm_state: str | None = None
    fsm_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UIAction:
    """Structured action for the Telegram UI."""

    text: str
    reply_markup: Any | None = None
    parse_mode: str | None = "Markdown"
    action_type: str = (
        "send_message"  # e.g., "send_message", "answer_callback", "edit_message"
    )
    show_thinking: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
