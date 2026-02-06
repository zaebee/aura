from pydantic import BaseModel, Field, PostgresDsn, RedisDsn


class DatabaseSettings(BaseModel):
    """Database configuration with required connection strings.

    Environment variables:
        AURA_DATABASE__URL: PostgreSQL connection string (required)
        AURA_DATABASE__REDIS_URL: Redis connection string (required)
        AURA_DATABASE__VECTOR_DIMENSION: Vector embedding dimension (default: 1024)
    """

    url: PostgresDsn = Field(...)  # type: ignore
    redis_url: RedisDsn = Field(...)  # type: ignore
    vector_dimension: int = 1024
