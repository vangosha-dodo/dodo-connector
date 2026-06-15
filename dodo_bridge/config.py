from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    api_keys: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("DODO_BRIDGE_API_KEYS", "API_KEYS"),
    )
    tool_registry_path: Path = Field(
        default=Path("configs/tools.example.yaml"),
        validation_alias="DODO_BRIDGE_TOOL_REGISTRY_PATH",
    )
    policy_path: Path = Field(
        default=Path("configs/policy.example.yaml"),
        validation_alias="DODO_BRIDGE_POLICY_PATH",
    )
    audit_db_path: Path = Field(
        default=Path("data/bridge.sqlite3"),
        validation_alias="DODO_BRIDGE_AUDIT_DB_PATH",
    )

    dodo_base_url: str = Field(
        default="https://api.dodois.io",
        validation_alias="DODO_BASE_URL",
    )
    dodo_country: str = Field(default="ru", validation_alias="DODO_COUNTRY")
    dodo_access_token: str | None = Field(default=None, validation_alias="DODO_ACCESS_TOKEN")

    superset_base_url: str | None = Field(default=None, validation_alias="SUPERSET_BASE_URL")
    superset_username: str | None = Field(default=None, validation_alias="SUPERSET_USERNAME")
    superset_password: str | None = Field(default=None, validation_alias="SUPERSET_PASSWORD")
    superset_access_token: str | None = Field(default=None, validation_alias="SUPERSET_ACCESS_TOKEN")

    dodo_auth_helper_command: str | None = Field(
        default=None,
        validation_alias="DODO_AUTH_HELPER_COMMAND",
    )
    dodo_auth_command_timeout_seconds: int = Field(
        default=180,
        validation_alias="DODO_AUTH_COMMAND_TIMEOUT_SECONDS",
    )

    @field_validator("api_keys", mode="before")
    @classmethod
    def parse_csv_list(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


def get_settings() -> Settings:
    return Settings()
