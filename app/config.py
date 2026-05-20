from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_URLS = {
    "app_base_url": "https://bot.paradigma-vpn.example",
    "marzban_base_url": "https://panel.paradigma-vpn.example",
    "public_site_url": "https://paradigma-vpn.example",
    "support_url": "https://t.me/paradigma_support",
    "terms_url": "https://paradigma-vpn.example/terms",
    "privacy_url": "https://paradigma-vpn.example/privacy",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: SecretStr = Field(default=SecretStr(""))
    app_env: Literal["local", "dev", "staging", "production"] = "local"
    app_base_url: AnyHttpUrl = DEFAULT_URLS["app_base_url"]
    webhook_secret: SecretStr = Field(default=SecretStr(""))
    webhook_path: str = "/telegram/webhook"

    database_url: str = "postgresql+asyncpg://paradigma:paradigma@postgres:5432/paradigma_vpn"
    redis_url: str | None = "redis://redis:6379/0"

    marzban_base_url: AnyHttpUrl = DEFAULT_URLS["marzban_base_url"]
    marzban_username: str = ""
    marzban_password: SecretStr = Field(default=SecretStr(""))
    marzban_verify_ssl: bool = True
    marzban_default_inbounds: str | None = None
    marzban_default_proxy_inbounds: str | None = None
    marzban_default_data_limit: int | None = 0
    marzban_default_data_limit_unlimited: bool = True
    marzban_default_data_limit_gb: int | None = None
    marzban_default_expire_days: int | None = None

    public_site_url: AnyHttpUrl = DEFAULT_URLS["public_site_url"]
    site_api_base_url: AnyHttpUrl | None = None
    telegram_auth_secret: SecretStr = Field(default=SecretStr(""))
    support_url: AnyHttpUrl = DEFAULT_URLS["support_url"]
    terms_url: AnyHttpUrl = DEFAULT_URLS["terms_url"]
    privacy_url: AnyHttpUrl = DEFAULT_URLS["privacy_url"]

    payment_provider: Literal["manual"] = "manual"
    payment_webhook_secret: SecretStr = Field(default=SecretStr(""))
    admin_telegram_ids: set[int] = Field(default_factory=set)

    trial_enabled: bool = True
    trial_duration_days: int = 3
    trial_traffic_limit_gb: int | None = None

    @field_validator(
        "app_base_url",
        "marzban_base_url",
        "public_site_url",
        "support_url",
        "terms_url",
        "privacy_url",
        mode="before",
    )
    @classmethod
    def empty_url_as_default(cls, value: object, info: ValidationInfo) -> object:
        if value == "":
            return DEFAULT_URLS[info.field_name]
        return value

    @field_validator("site_api_base_url", mode="before")
    @classmethod
    def empty_site_api_url_as_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("webhook_path")
    @classmethod
    def webhook_path_must_start_with_slash(cls, value: str) -> str:
        if not value.startswith("/"):
            msg = "WEBHOOK_PATH must start with /"
            raise ValueError(msg)
        return value

    @field_validator(
        "marzban_default_data_limit",
        "marzban_default_data_limit_gb",
        "marzban_default_expire_days",
        "trial_traffic_limit_gb",
        mode="before",
    )
    @classmethod
    def empty_optional_int_as_none(cls, value: object) -> object:
        return None if value == "" else value

    @property
    def marzban_issue_data_limit_bytes(self) -> int | None:
        if self.marzban_default_data_limit_unlimited:
            return 0
        if self.marzban_default_data_limit is not None:
            return self.marzban_default_data_limit
        if self.marzban_default_data_limit_gb is not None:
            return self.marzban_default_data_limit_gb * 1024 * 1024 * 1024
        return None

    @property
    def stored_traffic_limit_bytes(self) -> int | None:
        if self.marzban_default_data_limit_unlimited:
            return None
        return self.marzban_issue_data_limit_bytes

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> set[int]:
        if value in (None, ""):
            return set()
        if isinstance(value, int):
            return {value}
        if isinstance(value, set):
            return {int(item) for item in value}
        if isinstance(value, str):
            return {int(item.strip()) for item in value.split(",") if item.strip()}
        if isinstance(value, list | tuple):
            return {int(item) for item in value}
        msg = "ADMIN_TELEGRAM_IDS must be comma-separated integers"
        raise ValueError(msg)

    @property
    def webhook_url(self) -> str:
        return f"{str(self.app_base_url).rstrip('/')}{self.webhook_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
