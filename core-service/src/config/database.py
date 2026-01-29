from pydantic import BaseModel, Field, PostgresDsn, RedisDsn


class DatabaseSettings(BaseModel):
    url: PostgresDsn = Field("postgresql://user:password@localhost:5432/aura_db")
    redis_url: RedisDsn = Field("redis://localhost:6379/0")
    vector_dimension: int = 1024
