from pydantic import BaseModel


class VisualIdentity(BaseModel):
    primary_color: str
    secondary_color: str
    style: str


class VisionReportProps(BaseModel):
    asset_id: str
    name: str
    make: str | None = None
    model: str | None = None
    year: int | None = None
    confidence_score: float
    identity: VisualIdentity


class HeartbeatProps(BaseModel):
    timestamp: str
    event_count: int
    system_load: float
    identity: VisualIdentity


class ExportResult(BaseModel):
    artifact_id: str
    url: str
    mime_type: str = "video/mp4"
    size_bytes: int | None = None
