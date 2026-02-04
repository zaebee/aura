from typing import Any

from pydantic import BaseModel


class EventParams(BaseModel):
    topic: str
    payload: dict[str, Any]
