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
