import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis

from vk_to_commerceml.api import bot, oauth
from vk_to_commerceml.app_state import app_state
from vk_to_commerceml.bot.main import start_telegram, stop_telegram
from vk_to_commerceml.infrastructure.cml.client import CmlClient
from vk_to_commerceml.infrastructure.oauth_request_state_keys import OAuthRequestStateKeys
from vk_to_commerceml.infrastructure.secrets import Secrets
from vk_to_commerceml.infrastructure.vk.client import VkClient
from vk_to_commerceml.settings import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=logging.INFO)
    logger.info('🚀 Starting application')
    app_state.vk_client = VkClient()
    app_state.cml_client = CmlClient(settings.cml_debug_base_path)
    app_state.secrets = Secrets(settings.encryption_key)
    app_state.redis = Redis.from_url(str(settings.redis_url))
    app_state.oauth_request_state_keys = OAuthRequestStateKeys(app_state.redis)
    await start_telegram()
    yield
    logger.info('⛔ Stopping application')
    await stop_telegram()
    await app_state.redis.aclose()
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
