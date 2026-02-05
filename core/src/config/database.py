from pydantic import BaseModel, Field, PostgresDsn, RedisDsn


class DatabaseSettings(BaseModel):
    url: PostgresDsn = Field(...)  # type: ignore
    redis_url: RedisDsn = Field(...)  # type: ignore
    vector_dimension: int = 1024
