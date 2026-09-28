from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    vk_token: str
    vk_group_id: int
    vk_api_version: str = "5.199"
    vk_callback_secret: str = ""
    vk_confirmation_token: str = ""
    host: str = "0.0.0.0"
    port: int = 8000
    admin_ids: str = ""
    database_path: str = "data/baraholka.db"
    log_level: str = "INFO"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def administrators(self) -> set[int]:
        return {int(v.strip()) for v in self.admin_ids.split(",") if v.strip().isdigit()}

settings = Settings()
