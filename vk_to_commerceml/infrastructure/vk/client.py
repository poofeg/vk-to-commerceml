import asyncio
import contextlib
import logging
import os.path
from asyncio import Task
from operator import attrgetter
from typing import Optional, Union, Any, TypeVar, Type

import aiofiles
import aiofiles.os
from aiohttp import ClientSession, hdrs
from aiohttp.client_reqrep import json_re
from pydantic import ValidationError, SecretStr
from yarl import URL

from vk_to_commerceml.infrastructure.vk.models import MarketGetRoot, Photo, MarketItem, ErrorResponse, VkBaseModel, \
    MarketEditRoot, GroupsGetRoot, GroupItem

logger = logging.getLogger(__name__)
OAUTH_URL = 'https://oauth.vk.com/authorize'
VK_URL = URL('https://api.vk.com/method')
T_VkBaseModel = TypeVar('T_VkBaseModel', bound=VkBaseModel)


class VkClientSession:
    def __init__(self, session: ClientSession, access_token: SecretStr, tmp_dir: str) -> None:
        self.__session = session
        self.__access_token = access_token
        self.__tmp_dir = tmp_dir

    async def __request(self, response_model: Type[T_VkBaseModel], method: str, url: Union[str, URL],
                        **kwargs: Any) -> T_VkBaseModel:
        async with self.__session.request(method, url, **kwargs) as response:
            response.raise_for_status()
            content_type = response.content_type
            if json_re.match(content_type) is None:
                raise Exception(f'Unexpected Content-Type: {content_type}')
            data = await response.read()
            try:
                error_response = ErrorResponse.model_validate_json(data)
                raise Exception(error_response.error)
            except ValidationError:
                pass
            return response_model.model_validate_json(data)

    async def get_groups(self) -> list[GroupItem]:
        url = VK_URL / 'groups.get'
        params: dict[str, str] = {
            'access_token': self.__access_token.get_secret_value(),
            'extended': '1',
            'filter': 'advertiser',
            'v': '5.199',
        }
        root = await self.__request(
            GroupsGetRoot, hdrs.METH_GET, url, params=params
        )
        return root.response.items

    async def get_market(self, owner_id: int, with_disabled: bool) -> list[MarketItem]:
        url = VK_URL / 'market.get'
        page_size = 200
        common_params: dict[str, str] = {
            'access_token': self.__access_token.get_secret_value(),
            'owner_id': str(owner_id),
            'count': str(page_size),
            'extended': '1',
            'need_variants': '0',
            'with_disabled': str(int(with_disabled)),
            'v': '5.199',
        }

        async def get_page() -> list[MarketItem]:
            root = await self.__request(
                MarketGetRoot, hdrs.METH_GET, url, params=common_params | {'offset': str(page_size * page_number)}
            )
            return root.response.items
        result: list[MarketItem] = []
        page_number = 0
        while page := await get_page():
            result += page
            if len(page) < page_size:
                break
            page_number += 1
        return result

    async def get_market_product_by_id(self, owner_id: int, item_id: int) -> Optional[MarketItem]:
        url = VK_URL / 'market.getById'
        params: dict[str, str] = {
            'access_token': self.__access_token.get_secret_value(),
            'item_ids': f'{owner_id}_{item_id}',
            'extended': '1',
            'v': '5.199',
        }

        root = await self.__request(
            MarketGetRoot, hdrs.METH_GET, url, params=params
        )
        return root.response.items[0] if root.response.items else None

    async def edit_market_item(self, owner_id: int, item_id: int, description: str) -> bool:
        url = VK_URL / 'market.edit'
        data: dict[str, str] = {
            'access_token': self.__access_token.get_secret_value(),
            'owner_id': str(owner_id),
            'item_id': str(item_id),
            'description': description,
            'v': '5.199',
        }

        root = await self.__request(
            MarketEditRoot, hdrs.METH_POST, url, data=data
        )
        return bool(root.response)

    async def download_photos(self, photos: list[Photo], max_width: Optional[int] = None) -> dict[str, bytes]:
        async def download_single(name: str, url: str) -> tuple[str, bytes]:
            cache_path = os.path.join(self.__tmp_dir, name)
            if await aiofiles.os.path.exists(cache_path):
                async with aiofiles.open(cache_path, 'rb') as cache_file:
                    return name, await cache_file.read()
            async with self.__session.get(url) as response:
                response.raise_for_status()
                logger.info('Photo downloaded: %s', response.url)
                data = await response.read()
                async with aiofiles.open(cache_path, 'wb') as cache_file:
                    await cache_file.write(data)
                return name, await response.read()
        tasks: list[Task] = []
        async with asyncio.TaskGroup() as tg:
            for photo in photos:
                name = f'vk_{photo.id}.jpg'
                url = next(iter(size.url for size in sorted(photo.sizes, key=attrgetter('width'), reverse=True)
                                if not max_width or max_width >= size.width))
                tasks.append(tg.create_task(download_single(name, str(url))))
        result: dict[str, bytes] = {}
        for task in tasks:
            name, content = task.result()
            result[name] = content
        return result


class VkClient:
    def __init__(self) -> None:
        self.__session = ClientSession()
        self.__context_tmp_dir = contextlib.AsyncExitStack()
        self.__tmp_dir: str | None = None

    async def close(self) -> None:
        await self.__session.close()
        await self.__context_tmp_dir.aclose()

    async def get_access_token(self, client_id: str, client_secret: SecretStr, redirect_uri: str,
                               code: str) -> SecretStr:
        params: dict[str, str] = {
            'client_id': client_id,
            'client_secret': client_secret.get_secret_value(),
            'redirect_uri': redirect_uri,
            'code': code,
        }
        async with self.__session.post('https://oauth.vk.com/access_token', params=params) as response:
            response.raise_for_status()
            data = await response.json()
        return SecretStr(data['access_token'])

    async def get_session(self, access_token: SecretStr) -> VkClientSession:
        if not self.__tmp_dir:
            self.__tmp_dir = await self.__context_tmp_dir.enter_async_context(
                aiofiles.tempfile.TemporaryDirectory()
            )
            logger.info('Created temp directory: %s', self.__tmp_dir)
        return VkClientSession(self.__session, access_token, self.__tmp_dir)
