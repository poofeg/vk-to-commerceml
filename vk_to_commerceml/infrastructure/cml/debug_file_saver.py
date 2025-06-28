import logging
import os.path
import uuid
from datetime import datetime, UTC
from pathlib import Path

import aiofiles
import aiofiles.os

logger = logging.getLogger(__name__)


class DebugFileSaver:
    def __init__(self, base_path: Path | None) -> None:
        self.__base_path = base_path
        self.__target_dir: str | None = None

    async def create_dir(self) -> None:
        if not self.__base_path:
            return
        path = os.path.join(self.__base_path, str(uuid.uuid4()))
        await aiofiles.os.makedirs(path, exist_ok=True)
        self.__target_dir = os.path.abspath(path)
        logger.info(f"CML upload debug dir created: {self.__target_dir:}")

    async def save_file(self, filename: str, data: bytes | str) -> None:
        if not self.__target_dir:
            return
        now = datetime.now(UTC)
        file_path = os.path.join(self.__target_dir, f'{now:%Y%m%d_%H%M%S}_{filename}')

        if isinstance(data, str):
            data_bytes = data.encode()
        else:
            data_bytes = data

        try:
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(data_bytes)
        except Exception as e:
            logger.exception(f'Debug file save error: {e}')
