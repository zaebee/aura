from pydantic import BaseModel, Field, PostgresDsn, RedisDsn


class DatabaseSettings(BaseModel):
    url: PostgresDsn = Field("postgresql://user:password@localhost:5432/aura_db")  # type: ignore
    redis_url: RedisDsn = Field("redis://localhost:6379/0")  # type: ignore
    vector_dimension: int = 1024
