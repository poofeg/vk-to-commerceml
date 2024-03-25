import asyncio
import logging

from aiogram import Router, Dispatcher, Bot, types
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from vk_to_commerceml.app_state import app_state
from vk_to_commerceml.bot import connect, sync
from vk_to_commerceml.settings import settings

logger = logging.getLogger(__name__)

router = Router()
bot = Bot(token=settings.bot_token.get_secret_value())
task: asyncio.Task[None]


async def set_bot_commands_menu(my_bot: Bot) -> None:
    # Register commands for Telegram bot (menu)
    commands = [
        types.BotCommand(command="/sync", description='Запуск синхронизации'),
        types.BotCommand(command="/logout", description='Сбросить авторизации'),
    ]
    try:
        await my_bot.set_my_commands(commands)
    except Exception as e:
        logger.error(f"Can't set commands - {e}")


async def start_telegram() -> None:
    global task
    await set_bot_commands_menu(bot)
    app_state.bot_storage = RedisStorage(Redis.from_url(str(settings.redis_url)))
    dp = Dispatcher(storage=app_state.bot_storage)
    dp.include_router(sync.router)
    dp.include_router(connect.router)
    task = asyncio.create_task(dp._polling(bot, allowed_updates=['message', 'callback_query', 'inline_query']))


async def stop_telegram() -> None:
    task.cancel()
