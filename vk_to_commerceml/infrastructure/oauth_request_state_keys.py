from datetime import timedelta

from aiogram.fsm.storage.base import StorageKey
from pydantic import TypeAdapter
from redis.asyncio import Redis


class OAuthRequestStateKeys:
    _key_prefix = 'vk_oauth_state:'
    _ta_storage_key = TypeAdapter(StorageKey)

    def __init__(self, redis: Redis):
        self._redis = redis

    @classmethod
    def _gen_key(cls, state: str) -> str:
        return f'{cls._key_prefix}{state}'

    async def set(self, state: str, storage_key: StorageKey) -> None:
        value = self._ta_storage_key.dump_json(storage_key)
        await self._redis.set(self._gen_key(state), value, ex=timedelta(days=30))

    async def get(self, state: str, delete: bool = False) -> StorageKey | None:
        key = self._gen_key(state)
        if delete:
            value = await self._redis.getdel(key)
        else:
            value = await self._redis.get(key)
        if not value:
            return None
        return self._ta_storage_key.validate_json(value)

    async def delete(self, state: str) -> None:
        await self._redis.delete(self._gen_key(state))
