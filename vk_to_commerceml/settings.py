from pydantic import BaseModel, HttpUrl, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Vk(BaseModel):
    client_id: str
    client_secret: SecretStr
    oauth_callback_url: HttpUrl


class Settings(BaseSettings):
    bot_token: SecretStr = SecretStr('1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    base_url: HttpUrl = HttpUrl('http://127.0.0.1:8000')
    vk: Vk
    redis_url: RedisDsn = RedisDsn('redis://')
    encryption_key: bytes = b'change_me'

    model_config = SettingsConfigDict(
        env_nested_delimiter='__',
        nested_model_default_partial_update=True,
    )


settings = Settings()
