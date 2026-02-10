from typing import Protocol, cast, runtime_checkable

from pydantic import SecretStr

from .gen.aura.dna.v1 import (
    ActionType,
    AuditObservation,
    BeeObservation,
    Context,
    Event,
    NegotiationOffer,
    Observation,
    SearchResult,
    SystemVitals,
    VitalsStatus,
)
from .gen.aura.dna.v1 import (
    BeeContextData as BeeContext,
)
from .gen.aura.dna.v1 import (
    HiveContextData as HiveContext,
)
from .gen.aura.dna.v1 import (
    Intent as IntentAction,
)
from .gen.aura.dna.v1 import (
    TelegramContextData as TelegramContext,
)
from .gen.aura.dna.v1 import (
    UIIntent as UIAction,
)

__all__ = [
    "ActionType",
    "NegotiationOffer",
    "HiveContext",
    "Context",
    "IntentAction",
    "Observation",
    "Event",
    "SystemVitals",
    "VitalsStatus",
    "BeeContext",
    "TelegramContext",
    "AuditObservation",
    "UIAction",
    "SearchResult",
    "BeeObservation",
    "map_action",
    "get_action_name",
    "get_raw_key",
    "Signal",
]


def get_action_name(action_value: ActionType | str | int | None) -> str:
    """Safely retrieve the action name as a lowercase string."""
    if action_value is None:
        return "unspecified"
    if isinstance(action_value, str):
        return action_value.lower()
    if isinstance(action_value, int):
        try:
            return ActionType(action_value).name.lower().replace("action_type_", "")
        except ValueError:
            return "unknown"
    # ActionType enum member
    return action_value.name.lower().replace("action_type_", "")


def map_action(action_str: str | None) -> ActionType:
    """
    Standardized mapper for negotiation actions.
    Converts LLM strings to strict ActionType enum.
    """
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
    """
    if isinstance(key_field, SecretStr):
        return key_field.get_secret_value()
    return key_field


@runtime_checkable
class Signal(Protocol):
    """Protocol for inbound signals."""

    pass
