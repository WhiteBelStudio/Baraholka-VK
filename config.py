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
    moderator_ids: str = ""
    support_ids: str = ""
    database_path: str = "data/baraholka.db"
    log_level: str = "INFO"
    spam_window_seconds: int = Field(default=10, ge=1, le=300)
    spam_max_messages: int = Field(default=8, ge=1, le=100)
    spam_cooldown_seconds: int = Field(default=30, ge=1, le=3600)

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

    @staticmethod
    def _parse_ids(value: str) -> set[int]:
        return {
            int(item.strip())
            for item in value.split(",")
            if item.strip().isdigit()
        }

    @property
    def owners(self) -> set[int]:
        return self._parse_ids(self.admin_ids)

    @property
    def moderators(self) -> set[int]:
        return self._parse_ids(self.moderator_ids)

    @property
    def support(self) -> set[int]:
        return self._parse_ids(self.support_ids)

    @property
    def administrators(self) -> set[int]:
        return self.owners | self.moderators | self.support

    def role_for(self, user_id: int) -> str | None:
        if user_id in self.owners:
            return "owner"
        if user_id in self.moderators:
            return "moderator"
        if user_id in self.support:
            return "support"
        return None

    def can_moderate(self, user_id: int) -> bool:
        return user_id in self.owners or user_id in self.moderators

    def can_manage_users(self, user_id: int) -> bool:
        return user_id in self.owners

    def can_manage_roles(self, user_id: int) -> bool:
        return user_id in self.owners

    @property
    def database_file(self) -> Path:
        return Path(self.database_path)


settings = Settings()
