from typing import Optional

from pydantic import HttpUrl, BaseModel, RedisDsn, SecretStr
from pydantic_settings import BaseSettings


class Vk(BaseModel):
    client_id: str
    client_secret: SecretStr
    group_id: int
    oauth_callback_url: HttpUrl


class Settings(BaseSettings):
    bot_token: SecretStr = '1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    base_webhook_url: Optional[str] = None
    vk: Vk
    redis_url: RedisDsn = 'redis://'

    class Config:
        env_nested_delimiter = '__'


settings = Settings()
