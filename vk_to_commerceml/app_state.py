from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.redis import RedisStorage

from vk_to_commerceml.cml_client import CmlClient
from vk_to_commerceml.vk_client import VkClient


class AppState:
    vk_client: VkClient
    cml_client: CmlClient
    oauth_request_state_keys: dict[str, StorageKey] = {}
    bot_storage: RedisStorage


app_state = AppState()
