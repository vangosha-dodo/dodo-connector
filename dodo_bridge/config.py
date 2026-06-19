from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
        enable_decoding=False,
    )

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
    dodo_data_max_period_days: int = Field(
        default=92,
        validation_alias="DODO_DATA_MAX_PERIOD_DAYS",
    )
    dodo_data_default_take: int = Field(
        default=500,
        validation_alias="DODO_DATA_DEFAULT_TAKE",
    )
    dodo_data_max_take: int = Field(
        default=1000,
        validation_alias="DODO_DATA_MAX_TAKE",
    )
    dodo_data_default_max_pages: int = Field(
        default=5,
        validation_alias="DODO_DATA_DEFAULT_MAX_PAGES",
    )
    dodo_data_max_pages: int = Field(
        default=20,
        validation_alias="DODO_DATA_MAX_PAGES",
    )
    dodo_data_max_rows: int = Field(
        default=5000,
        validation_alias="DODO_DATA_MAX_ROWS",
    )
    dodo_pizzerias_path: Path | None = Field(
        default=None,
        validation_alias="DODO_PIZZERIAS_PATH",
    )

    superset_base_url: str | None = Field(default=None, validation_alias="SUPERSET_BASE_URL")
    superset_username: str | None = Field(default=None, validation_alias="SUPERSET_USERNAME")
    superset_password: str | None = Field(default=None, validation_alias="SUPERSET_PASSWORD")
    superset_access_token: str | None = Field(default=None, validation_alias="SUPERSET_ACCESS_TOKEN")
    superset_session_cookies_path: Path | None = Field(
        default=None,
        validation_alias="SUPERSET_SESSION_COOKIES_PATH",
    )
    superset_browser_helper_command: str | None = Field(
        default=None,
        validation_alias="SUPERSET_BROWSER_HELPER_COMMAND",
    )
    superset_browser_command_timeout_seconds: int = Field(
        default=180,
        validation_alias="SUPERSET_BROWSER_COMMAND_TIMEOUT_SECONDS",
    )

    dodo_auth_helper_command: str | None = Field(
        default=None,
        validation_alias="DODO_AUTH_HELPER_COMMAND",
    )
    dodo_auth_command_timeout_seconds: int = Field(
        default=180,
        validation_alias="DODO_AUTH_COMMAND_TIMEOUT_SECONDS",
    )
    dodo_kb_auth_helper_command: str | None = Field(
        default=None,
        validation_alias="DODO_KB_AUTH_HELPER_COMMAND",
    )
    dodo_kb_auth_command_timeout_seconds: int = Field(
        default=300,
        validation_alias="DODO_KB_AUTH_COMMAND_TIMEOUT_SECONDS",
    )
    dodo_office_manager_helper_command: str | None = Field(
        default=None,
        validation_alias="DODO_OFFICE_MANAGER_HELPER_COMMAND",
    )
    dodo_office_manager_command_timeout_seconds: int = Field(
        default=300,
        validation_alias="DODO_OFFICE_MANAGER_COMMAND_TIMEOUT_SECONDS",
    )
    automation_google_sheets_write_enabled: bool = Field(
        default=False,
        validation_alias="AUTOMATION_GOOGLE_SHEETS_WRITE_ENABLED",
    )
    courier_payroll_spreadsheet_id: str = Field(
        default="1eq81n7NL7hgmSYYm6RRwA1-zlRnsBeXX0QW7uuN2dHU",
        validation_alias="COURIER_PAYROLL_SPREADSHEET_ID",
    )

    @field_validator("api_keys", mode="before")
    @classmethod
    def parse_csv_list(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("superset_session_cookies_path", mode="before")
    @classmethod
    def blank_path_to_none(cls, value: Any) -> Any:
        if value == "":
            return None
        return value

    @field_validator(
        "superset_browser_helper_command",
        "dodo_auth_helper_command",
        "dodo_kb_auth_helper_command",
        "dodo_office_manager_helper_command",
        mode="before",
    )
    @classmethod
    def blank_string_to_none(cls, value: Any) -> Any:
        if value == "":
            return None
        return value


def get_settings() -> Settings:
    return Settings()
