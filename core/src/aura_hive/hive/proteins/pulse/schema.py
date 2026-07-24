from typing import Any

from pydantic import BaseModel


class EventParams(BaseModel):
    """Deprecated: Use typed event params instead."""

    topic: str
    payload: dict[str, Any]


class NegotiationEventParams(BaseModel):
    """Params for emit_negotiation intent."""

    session_token: str
    action: str  # accept, counter, reject
    price: float
    item_id: str
    agent_did: str


class VitalsEventParams(BaseModel):
    """Params for emit_vitals intent."""

    service: str
    cpu_usage: float
    memory_usage: float
    status: str = "ok"


class AlertEventParams(BaseModel):
    """Params for emit_alert intent."""

    severity: str  # info, warning, error, critical
    message: str
    source: str


class AuditEventParams(BaseModel):
    """Params for emit_audit intent."""

    repo_name: str
    is_pure: bool
    heresies: list[str] = []
    negotiation_success_rate: float = 0.0
