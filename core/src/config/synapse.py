from pydantic import BaseModel, Field


class SynapseSettings(BaseModel):
    enabled: bool = False
    active_synapses: list[str] = Field(default_factory=list)
