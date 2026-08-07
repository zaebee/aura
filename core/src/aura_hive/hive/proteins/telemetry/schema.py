from typing import Any

from pydantic import BaseModel


class MetricIncrementParams(BaseModel):
    name: str
    labels: dict[str, Any] = {}


class HealthResponse(BaseModel):
    status: str
    details: dict[str, Any] = {}


class LokiQueryParams(BaseModel):
    query: str
    limit: int = 100


class PrometheusQueryParams(BaseModel):
    query: str


class K8sHealthParams(BaseModel):
    namespace: str = "default"
