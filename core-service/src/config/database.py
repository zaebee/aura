from pydantic import AliasChoices, BaseModel, Field, PostgresDsn, RedisDsn


class DatabaseSettings(BaseModel):
    url: PostgresDsn = Field(
        "postgresql://user:password@localhost:5432/aura_db",
        validation_alias=AliasChoices(
            "AURA_DATABASE__URL", "AURA_DB__URL", "DATABASE_URL"
        ),
    )
    redis_url: RedisDsn = Field(
        "redis://localhost:6379/0",
        validation_alias=AliasChoices("AURA_DATABASE__REDIS_URL", "REDIS_URL"),
    )
    vector_dimension: int = 1024
