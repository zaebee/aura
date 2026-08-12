from typing import Any

from pydantic import BaseModel


class ValidationParams(BaseModel):
    decision: dict[str, Any]
    context: dict[str, Any]


class SafePriceParams(BaseModel):
    context: dict[str, Any]
    reason: str = ""
    request_id: str = ""


class VisionValidationParams(BaseModel):
    vision_result: dict[str, Any]
