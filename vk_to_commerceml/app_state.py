from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.redis import RedisStorage

from vk_to_commerceml.infrastructure.cml.client import CmlClient
from vk_to_commerceml.infrastructure.secrets import Secrets
from vk_to_commerceml.infrastructure.vk.client import VkClient


class AppState:
    vk_client: VkClient
    cml_client: CmlClient
    oauth_request_state_keys: dict[str, StorageKey] = {}
    bot_storage: RedisStorage
    secrets: Secrets


app_state = AppState()
