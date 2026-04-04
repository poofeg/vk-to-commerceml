from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from vk_to_commerceml.infrastructure.cml.client import CmlClient
from vk_to_commerceml.infrastructure.oauth_request_state_keys import OAuthRequestStateKeys
from vk_to_commerceml.infrastructure.secrets import Secrets
from vk_to_commerceml.infrastructure.vk.client import VkClient


class AppState:
    vk_client: VkClient
    cml_client: CmlClient
    oauth_request_state_keys: OAuthRequestStateKeys
    bot_storage: RedisStorage
    secrets: Secrets
    redis: Redis


app_state = AppState()
