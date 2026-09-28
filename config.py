from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    vk_token: str = Field(min_length=1)
    vk_group_id: int
    vk_api_version: str = "5.199"
    vk_callback_secret: str = ""
    vk_confirmation_token: str = ""

    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)

    admin_ids: str = ""
    database_path: str = "data/baraholka.db"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("vk_api_version", "log_level", mode="before")
    @classmethod
    def normalize_strings(cls, value: object) -> str:
        return str(value).strip()

    @field_validator("database_path")
    @classmethod
    def validate_database_path(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("DATABASE_PATH must not be empty")
        return value

    @property
    def administrators(self) -> set[int]:
        return {
            int(value.strip())
            for value in self.admin_ids.split(",")
            if value.strip().isdigit()
        }

    @property
    def database_file(self) -> Path:
        return Path(self.database_path)


settings = Settings()
