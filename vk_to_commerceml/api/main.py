import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from vk_to_commerceml.api import bot, oauth
from vk_to_commerceml.app_state import app_state
from vk_to_commerceml.bot.main import start_telegram, stop_telegram
from vk_to_commerceml.cml_client import CmlClient
from vk_to_commerceml.settings import settings
from vk_to_commerceml.vk_client import VkClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=logging.INFO)
    logger.info('🚀 Starting application')
    app_state.vk_client = VkClient()
    app_state.cml_client = CmlClient(
        url=str(settings.cml.url),
        login=settings.cml.login,
        password=settings.cml.password,
    )
    await start_telegram()
    yield
    logger.info('⛔ Stopping application')
    await stop_telegram()
    await app_state.cml_client.close()
    await app_state.vk_client.close()


app = FastAPI(
    title='vk-to-commerceml',
    lifespan=lifespan,
)
app.include_router(bot.router)
app.include_router(oauth.router)


@app.get('/', include_in_schema=False)
async def docs_redirect() -> RedirectResponse:
    return RedirectResponse(url='/docs')
