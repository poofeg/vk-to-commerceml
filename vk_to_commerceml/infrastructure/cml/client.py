import asyncio
import itertools
import logging

from aiohttp import ClientSession, BasicAuth, hdrs, TCPConnector
from pydantic import SecretStr
from yarl import URL

from vk_to_commerceml.infrastructure.cml.models import ImportDocument, OffersDocument

logger = logging.getLogger(__name__)


class CmlClientSession:
    def __init__(self, connector: TCPConnector, url: str, login: str, password: SecretStr) -> None:
        self.__url = URL(url)
        self.__login = login
        self.__password = password
        self.__connector = connector

    async def __import(self, session: ClientSession, filename: str) -> bool:
        logger.info('CommerceML: import %s', filename)
        for sleep_delay in itertools.count(start=1):
            async with session.get(
                self.__url,
                params={'type': 'catalog', 'mode': 'import', 'filename': filename},
            ) as response:
                response.raise_for_status()
                result = (await response.text()).strip()
                logger.info('Response: %s', result)
            if result == 'progress':
                await asyncio.sleep(sleep_delay)
                continue
            return result == 'success'

    async def upload(self, import_document: ImportDocument,
                     offers_document: OffersDocument | None = None,
                     photos: dict[str, bytes] | None = None) -> bool:
        async with ClientSession(connector=self.__connector, connector_owner=False) as session:
            logger.info(
                'CommerceML: checkauth, url: %s, login: %s, password: %s', self.__url, self.__login, self.__password
            )
            async with session.get(
                self.__url,
                params={'type': 'catalog', 'mode': 'checkauth'},
                auth=BasicAuth(login=self.__login, password=self.__password.get_secret_value(), encoding='utf8'),
            ) as response:
                response.raise_for_status()

            logger.info('CommerceML: init')
            async with session.get(self.__url, params={'type': 'catalog', 'mode': 'init'}) as response:
                response.raise_for_status()
                logger.info('Response: %s', await response.text())

            if photos:
                for photo_name, photo_data in photos.items():
                    logger.info('CommerceML: file %s', photo_name)
                    async with session.post(
                        self.__url,
                        params={'type': 'catalog', 'mode': 'file', 'filename': photo_name},
                        data=photo_data,
                        headers={hdrs.CONTENT_TYPE: 'image/jpeg'},
                    ) as response:
                        response.raise_for_status()
                        logger.info('Response: %s', await response.text())

            logger.info('CommerceML: file import.xml')
            async with session.post(
                self.__url,
                params={'type': 'catalog', 'mode': 'file', 'filename': 'import.xml'},
                data=import_document.to_xml(pretty_print=True, encoding='UTF-8', standalone=True),
                headers={hdrs.CONTENT_TYPE: 'application/xml; charset=utf-8'},
            ) as response:
                response.raise_for_status()
                logger.info('Response: %s', await response.text())

            if offers_document:
                logger.info('CommerceML: file offers.xml')
                async with session.post(
                    self.__url,
                    params={'type': 'catalog', 'mode': 'file', 'filename': 'offers.xml'},
                    data=offers_document.to_xml(pretty_print=True, encoding='UTF-8', standalone=True),
                    headers={hdrs.CONTENT_TYPE: 'application/xml; charset=utf-8'},
                ) as response:
                    response.raise_for_status()
                    logger.info('Response: %s', await response.text())

            await self.__import(session, 'import.xml')
            if offers_document:
                await self.__import(session, 'offers.xml')
            return True


class CmlClient:
    def __init__(self) -> None:
        self.__connector = TCPConnector()

    async def close(self) -> None:
        await self.__connector.close()

    async def get_session(self, url: str, login: str, password: SecretStr) -> CmlClientSession:
        return CmlClientSession(self.__connector, url, login, password)
