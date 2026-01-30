from pydantic import BaseModel, Field


class DatabaseSettings(BaseModel):
    url: str = Field("postgresql://user:password@localhost:5432/aura_db")
    redis_url: str = Field("redis://localhost:6379/0")
    vector_dimension: int = 1024
