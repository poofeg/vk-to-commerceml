import io
import itertools
import logging
import re
from io import BytesIO
from typing import cast
from zipfile import ZipFile

from aiohttp import ClientSession, BasicAuth, hdrs, TCPConnector
from pydantic import SecretStr
from yarl import URL

from vk_to_commerceml.infrastructure.cml.models import ImportDocument, OffersDocument

logger = logging.getLogger(__name__)
RE_FILE_LIMIT = re.compile(r'^file_limit=(\d+)$', re.MULTILINE)


class CmlClientSession:
    def __init__(self, connector: TCPConnector, url: str, login: str, password: SecretStr) -> None:
        self.__url = URL(url)
        self.__login = login
        self.__password = password
        self.__connector = connector

    async def __import(self, session: ClientSession, filename: str, common_params: dict[str, str]) -> None:
        logger.info('CommerceML: import %s', filename)
        for sleep_delay in itertools.count(start=1):
            async with session.get(
                self.__url,
                params={**common_params, 'mode': 'import', 'filename': filename},
            ) as response:
                response.raise_for_status()
                result = (await response.text()).strip()
                logger.info('Response: %s', result)
            if result.startswith('progress') or 'Too many requests' in result:
                await asyncio.sleep(sleep_delay)
                continue
            break
        if not result.startswith('success'):
            raise Exception(result)

    async def __file(self, session: ClientSession, filename: str, common_params: dict[str, str],
                     content_type: str, data: io.BytesIO | bytes, file_limit: int | None = None) -> None:
        if file_limit:
            if isinstance(data, io.BytesIO):
                for chunk in itertools.batched(data.getbuffer(), file_limit):
                    await self.__file(session, filename, common_params, content_type, bytes(chunk))
            else:
                for chunk in itertools.batched(data, file_limit):
                    await self.__file(session, filename, common_params, content_type, bytes(chunk))
            return
        logger.info('CommerceML: file %s', filename)
        async with session.post(
            self.__url,
            params={**common_params, 'mode': 'file', 'filename': filename},
            data=data,
            headers={hdrs.CONTENT_TYPE: content_type},
        ) as response:
            response.raise_for_status()
            result = (await response.text()).strip()
        logger.info('Response: %s', result)
        if not result.startswith('success'):
            raise Exception(result)

    async def upload(self, import_document: ImportDocument,
                     offers_document: OffersDocument | None = None,
                     photos: dict[str, bytes] | None = None) -> None:
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
                auth_response = (await response.text()).splitlines()
            logger.info('Response: %s', auth_response)
            if not auth_response or auth_response[0].startswith('failure'):
                raise Exception('Auth error')
            common_params = {'type': 'catalog'}
            if len(auth_response) >= 4 and auth_response[3].startswith('sessid='):
                common_params['sessid'] = auth_response[3].removeprefix('sessid=')

            logger.info('CommerceML: init')
            async with session.get(self.__url, params={**common_params, 'mode': 'init'}) as response:
                response.raise_for_status()
                response_text = await response.text()
            logger.info('Response: %s', response_text)
            zip_bytes = BytesIO()
            zip_file = ZipFile(zip_bytes, 'w') if 'zip=yes' in response_text else None
            file_limit: int | None = None
            if m := RE_FILE_LIMIT.search(response_text):
                file_limit = int(m.group(1))

            if photos:
                for photo_name, photo_data in photos.items():
                    if zip_file:
                        logger.info('Add file to zip: %s', photo_name)
                        zip_file.writestr(photo_name, photo_data)
                    else:
                        await self.__file(
                            session=session,
                            filename=photo_name,
                            common_params=common_params,
                            content_type='image/jpeg',
                            data=photo_data,
                            file_limit=file_limit,
                        )

            import_xml = cast(bytes, import_document.to_xml(pretty_print=True, encoding='UTF-8', standalone=True))
            if zip_file:
                logger.info('Add file to zip: import.xml')
                zip_file.writestr('import.xml', import_xml)
            else:
                await self.__file(
                    session=session,
                    filename='import.xml',
                    common_params=common_params,
                    content_type='application/xml; charset=utf-8',
                    data=import_xml,
                    file_limit=file_limit,
                )

            if offers_document:
                offers_xml = cast(bytes, offers_document.to_xml(pretty_print=True, encoding='UTF-8', standalone=True))
                if zip_file:
                    logger.info('Add file to zip: offers.xml')
                    zip_file.writestr('offers.xml', offers_xml)
                else:
                    await self.__file(
                        session=session,
                        filename='offers.xml',
                        common_params=common_params,
                        content_type='application/xml; charset=utf-8',
                        data=offers_xml,
                        file_limit=file_limit,
                    )

            if zip_file:
                zip_file.close()
                zip_bytes.seek(0)
                await self.__file(
                    session=session,
                    filename='stock.zip',
                    common_params=common_params,
                    content_type='application/zip',
                    data=zip_bytes,
                    file_limit=file_limit,
                )
                zip_bytes.close()

            await self.__import(session, 'import.xml', common_params)
            if offers_document:
                await self.__import(session, 'offers.xml', common_params)


class CmlClient:
    def __init__(self) -> None:
        self.__connector = TCPConnector()

    async def close(self) -> None:
        await self.__connector.close()

    async def get_session(self, url: str, login: str, password: SecretStr) -> CmlClientSession:
        return CmlClientSession(self.__connector, url, login, password)
