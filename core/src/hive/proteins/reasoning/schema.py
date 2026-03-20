from typing import Any

from pydantic import BaseModel


class NegotiationParams(BaseModel):
    bid: float
    context: dict[str, Any] = {}
    history: list[dict[str, Any]] = []


class EmbeddingParams(BaseModel):
    text: str


class NegotiationResult(BaseModel):
    action: str
    price: float
    message: str
    thought: str = ""
    metadata: dict[str, Any] = {}


class TradeParams(BaseModel):
    market_context: dict[str, Any] = {}
    system_vitals: dict[str, Any] = {}
    current_treasury: dict[str, Any] = {}
    risk_threshold: float = 0.10
