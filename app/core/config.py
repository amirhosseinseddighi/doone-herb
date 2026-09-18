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
        env_file_encoding="utf-8",
        extra="ignore"
    )

    REDIS_URL: RedisDsn
    JWT_SECRET: SecretStr
    JWT_ALGORITHM: str = Field("HS256", validation_alias='jwt_algo')
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 90
    POSTGRES_USER: str
    POSTGRES_PASSWORD: SecretStr
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int

    # CART
    GUEST_CART_MAX_AGE: int = 30 * 24 * 3600

    # IMAGE VARIABLES
    MAX_IMAGE_SIZE_MEGA_BYTE: int = 5

    # PRODUCT IMAGE
    PRODUCT_IMAGE_UPLOAD_DIRECTORY: str = "media/products"

    # CATEGORY IMAGE
    CATEGORY_IMAGE_UPLOAD_DIRECTORY: str = "media/categories"


    # Email-related variables
    MAIL_SERVER: str = "sandbox.smtp.mailtrap.io"
    MAIL_PORT: int = 2525
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: SecretStr = SecretStr("")
    MAIL_FROM: str = "from@example.com"
    MAIL_USE_TLS: bool = False
    MAIL_START_TLS: bool = True

    # reset password functionality
    RESET_TOKEN_PREFIX: str = "pwd_reset:"
    RESET_TOKEN_TTL_SECONDS: int = 3600  # 60 minutes

    FRONTEND_URL: str = "http://localhost:7000"

    @property
    def database_url(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD.get_secret_value(),
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

settings = Settings()