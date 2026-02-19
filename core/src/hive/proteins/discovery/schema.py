from typing import Optional, List
from pydantic import BaseModel, Field

class ScanParams(BaseModel):
    query: str = Field(..., description="GitHub search query")

class SequenceParams(BaseModel):
    repo_url: str = Field(..., description="Full URL of the GitHub repository")

class AnalysisParams(BaseModel):
    repo_context: str = Field(..., description="Textual context of the repository (README, protos, etc.)")

class FirstContactParams(BaseModel):
    query: str = Field(..., description="GitHub search query to find and contact compatible organisms")
