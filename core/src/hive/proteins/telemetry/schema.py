from typing import Any

from pydantic import BaseModel


class MetricIncrementParams(BaseModel):
    name: str
    labels: dict[str, Any] = {}


class HealthResponse(BaseModel):
    status: str
    details: dict[str, Any] = {}
