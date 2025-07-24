import asyncio
import io
import itertools
import logging
import re
from io import BytesIO
from pathlib import Path
from typing import cast
from zipfile import ZipFile

from aiohttp import BasicAuth, ClientSession, TCPConnector, hdrs
from pydantic import SecretStr
from yarl import URL

from vk_to_commerceml.infrastructure.cml.debug_file_saver import DebugFileSaver
from vk_to_commerceml.infrastructure.cml.models import ImportDocument, OffersDocument

logger = logging.getLogger(__name__)
RE_FILE_LIMIT = re.compile(r'^\s*file_limit\s*=\s*(\d+)\s*$', re.MULTILINE)
RE_ZIP = re.compile(r'^\s*zip\s*=\s*yes\s*$', re.MULTILINE)
RE_STATUS = re.compile(r'^\s*(?P<status>success|failure|progress)\s*(?P<detail>.*)$', re.DOTALL)


class CmlClientSession:
    def __init__(
        self, connector: TCPConnector, url: str, login: str, password: SecretStr,
        debug_file_saver: DebugFileSaver
    ) -> None:
        self.__url = URL(url)
        self.__login = login
        self.__password = password
        self.__connector = connector
        self.__debug_file_saver = debug_file_saver

    async def __import(self, session: ClientSession, filename: str, common_params: dict[str, str]) -> None:
        logger.info('CommerceML: import %s', filename)
        status = 'failure'
        detail = ''
        for sleep_delay in itertools.count(start=1):
            async with session.get(
                self.__url,
                params={**common_params, 'mode': 'import', 'filename': filename},
            ) as response:
                response.raise_for_status()
                result = (await response.text()).strip()
                logger.info('Response: %s', result)
            if m := RE_STATUS.match(result):
                status = m.group('status')
                prev_detail = detail
                detail = m.group('detail')
                if 'Too many requests' in detail:
                    await asyncio.sleep(sleep_delay)
                    continue
                if status == 'progress':
                    if detail == prev_detail:
                        await asyncio.sleep(sleep_delay)
                    continue
            break
        if status != 'success':
            raise Exception(detail)

    async def __file(self, session: ClientSession, filename: str, common_params: dict[str, str],
                     content_type: str, data: io.BytesIO | bytes, file_limit: int | None = None) -> None:
        if isinstance(data, io.BytesIO):
            data_bytes = data.getvalue()
        else:
            data_bytes = data

        if not content_type.startswith('image/'):
            await self.__debug_file_saver.save_file(filename, data_bytes)

        if file_limit:
            for chunk_number, chunk in enumerate(itertools.batched(data_bytes, file_limit)):
                await self.__upload_file_chunk(
                    session, filename, common_params, content_type, bytes(chunk), chunk_number
                )
        else:
            await self.__upload_file_chunk(session, filename, common_params, content_type, data_bytes)

    async def __upload_file_chunk(
        self, session: ClientSession, filename: str, common_params: dict[str, str],
        content_type: str, data: bytes, chunk_number: int = 0
    ) -> None:
        logger.info('CommerceML: file %s, chunk number: %s', filename, chunk_number)
        async with session.post(
            self.__url,
            params={**common_params, 'mode': 'file', 'filename': filename},
            data=data,
            headers={hdrs.CONTENT_TYPE: content_type},
        ) as response:
            response.raise_for_status()
            result = (await response.text()).strip()
        logger.info('Response: %s', result)
        if not (m := RE_STATUS.match(result)) or m.group('status') != 'success':
            raise Exception(result)

    async def __check_auth(self, session: ClientSession) -> str | None:
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
            raise Exception('\n'.join(auth_response[1:]) or 'Auth error')
        if len(auth_response) >= 4 and auth_response[3].startswith('sessid='):
            return auth_response[3].removeprefix('sessid=')
        return None

    async def __init(self, session: ClientSession, common_params: dict[str, str]) -> tuple[bool, int | None]:
        logger.info('CommerceML: init')
        async with session.get(self.__url, params={**common_params, 'mode': 'init'}) as response:
            response.raise_for_status()
            response_text = await response.text()
        logger.info('Response: %s', response_text)
        zip_yes = bool(RE_ZIP.search(response_text))
        file_limit: int | None = None
        if m := RE_FILE_LIMIT.search(response_text):
            file_limit = int(m.group(1))
        return zip_yes, file_limit

    async def check_auth(self) -> None:
        async with ClientSession(connector=self.__connector, connector_owner=False) as session:
            await self.__check_auth(session)

    async def upload(self, import_document: ImportDocument,
                     offers_document: OffersDocument | None = None,
                     photos: dict[str, bytes] | None = None) -> None:
        async with ClientSession(connector=self.__connector, connector_owner=False) as session:
            sessid = await self.__check_auth(session)

            common_params = {'type': 'catalog'}
            if sessid:
                common_params['sessid'] = sessid

            zip_yes, file_limit = await self.__init(session, common_params)
            if zip_yes:
                zip_bytes = BytesIO()
                zip_file = ZipFile(zip_bytes, 'w')

            if photos:
                for photo_name, photo_data in photos.items():
                    if zip_yes:
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
            if zip_yes:
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
                if zip_yes:
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

            if zip_yes:
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
    def __init__(self, debug_base_path: Path | None = None) -> None:
        self.__connector = TCPConnector()
        self.__debug_base_path = debug_base_path

    async def close(self) -> None:
        await self.__connector.close()

    async def get_session(self, url: str, login: str, password: SecretStr) -> CmlClientSession:
        debug_file_saver = DebugFileSaver(self.__debug_base_path)
        await debug_file_saver.create_dir()
        return CmlClientSession(self.__connector, url, login, password, debug_file_saver)
