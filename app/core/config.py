from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./queuealign.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    secret_key: str = "dev-secret-change-me"
    frontend_url: str = "http://localhost:5173"
    desk_token_hours: int = 12

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
