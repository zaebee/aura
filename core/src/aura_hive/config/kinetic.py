from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class KineticSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AURA_KINETIC__",
        extra="ignore",
    )

    remotion_project_path: str = Field("./remotion-app")
    output_dir: str = Field("./artifacts/kinetic")
