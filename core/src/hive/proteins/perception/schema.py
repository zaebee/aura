from typing import Any
from pydantic import BaseModel


class PerceiveImageParams(BaseModel):
    image_bytes: bytes


class PerceiveImageResult(BaseModel):
    item: dict[str, Any]
