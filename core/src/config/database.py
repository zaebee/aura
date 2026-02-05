from pydantic import BaseModel, Field, PostgresDsn, RedisDsn, model_validator


class DatabaseSettings(BaseModel):
    """Database configuration with required connection strings.

    Environment variables:
        AURA_DATABASE__URL: PostgreSQL connection string (required)
        AURA_DATABASE__REDIS_URL: Redis connection string (required)
        AURA_DATABASE__VECTOR_DIMENSION: Vector embedding dimension (default: 1024)
    """

    url: PostgresDsn = Field(default=None)  # type: ignore
    redis_url: RedisDsn = Field(default=None)  # type: ignore
    vector_dimension: int = 1024

    @model_validator(mode="after")
    def validate_required(self) -> "DatabaseSettings":
        if not self.url:
            raise ValueError(
                "AURA_DATABASE__URL is required. "
                "Example: postgresql://user:pass@host:5432/dbname"
            )
        if not self.redis_url:
            raise ValueError(
                "AURA_DATABASE__REDIS_URL is required. Example: redis://host:6379/0"
            )
        return self
