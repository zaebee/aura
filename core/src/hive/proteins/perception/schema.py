from typing import Any
from pydantic import BaseModel


class PerceiveImageParams(BaseModel):
    image_bytes: bytes


class PerceiveImageResult(BaseModel):
    # Flexible result for perception
    make: str | None = None
    model: str | None = None
    year: int | None = None
    color: str | None = None
    estimated_price: float | None = None
    confidence_score: float | None = None

    # Item-like mapping
    id: str | None = None
    name: str | None = None
    base_price: float | None = None
    floor_price: float | None = None
    meta: dict[str, Any] | None = None
