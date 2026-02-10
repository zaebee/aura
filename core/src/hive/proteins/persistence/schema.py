from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ItemSchema(BaseModel):
    """Pydantic model for inventory items."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    base_price: float
    floor_price: float
    is_active: bool = True
    meta: dict[str, Any] = {}


class DealSchema(BaseModel):
    """Pydantic model for locked deals."""

    model_config = ConfigDict(from_attributes=True)

    id: Any
    identifier: str
    item_name: str
    final_price: float
    currency: str
    payment_memo: str
    status: str
    buyer_did: str | None = None
    expires_at: datetime
    transaction_hash: str | None = None
    paid_at: datetime | None = None


class ReadItemParams(BaseModel):
    identifier: str | None = None
    item_id: str | None = None


class CreateDealParams(BaseModel):
    id: Any
    identifier: str | None = None
    item_id: str | None = None
    item_name: str
    final_price: float
    currency: str
    payment_memo: str
    secret_content: bytes
    buyer_did: str | None = None
    expires_at: datetime


class VectorSearchParams(BaseModel):
    query_vector: list[float]
    limit: int = 5
    min_similarity: float | None = None
