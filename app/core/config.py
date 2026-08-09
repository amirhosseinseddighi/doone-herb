from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import (
    AliasChoices,
    Field,
    PostgresDsn,
    RedisDsn,
    SecretStr
)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

    DATABASE_URL: PostgresDsn
    REDIS_URL: RedisDsn
    JWT_SECRET: SecretStr
    JWT_ALGORITHM: str = Field("HS256", validation_alias='jwt_algo')
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 90



settings = Settings()