import asyncio
import logging
from datetime import datetime
from importlib import resources
from secrets import token_urlsafe

from aiogram import Router, Dispatcher, Bot, types, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hbold
from redis.asyncio import Redis
from yarl import URL

from vk_to_commerceml.app_state import app_state
from vk_to_commerceml.services.sync import SyncService, SyncState
from vk_to_commerceml.settings import settings

logger = logging.getLogger(__name__)

router = Router()
bot = Bot(token=settings.bot_token.get_secret_value())
task: asyncio.Task[None]

OAUTH_URL = 'https://oauth.vk.com/authorize'


class Form(StatesGroup):
    authorized = State()


class SyncCallback(CallbackData, prefix='sync'):
    with_disabled: bool = False
    with_photos: bool = False
    start: bool = False


@router.callback_query(Form.authorized, SyncCallback.filter(F.start))
async def callback_sync(query: types.CallbackQuery, callback_data: SyncCallback, state: FSMContext) -> None:
    started_at = datetime.now()
    data = await state.get_data()
    vk_token = data['vk_token']
    await state.update_data(sync=callback_data.model_dump_json(exclude={'start'}))
    sync_service = SyncService(app_state.cml_client, app_state.vk_client, vk_token)
    await query.answer('Запуск синхронизации')
    await query.message.answer('Запуск синхронизации')
    try:
        async for status, content in sync_service.sync(
            callback_data.with_disabled, callback_data.with_photos, skip_multiple_group=True
        ):
            match status:
                case SyncState.GET_PRODUCTS_SUCCESS:
                    await query.message.answer(f'Из ВК успешно получено {content} товаров')
                case SyncState.GET_PRODUCTS_FAILED:
                    await query.message.answer(f'Ошибка получения товаров из ВК: {content}')
                case SyncState.MAIN_SUCCESS:
                    csv_file = types.BufferedInputFile(content.encode('utf8'), filename='categories.csv')
                    caption = 'Товары успешно отправлены на сайт. Чтобы проставить категорию новым товарам нужно ' \
                              f'загрузить CSV-файл ниже на {settings.cml.catalog_url}, ' \
                              'иначе они будут без категории.'
                    await query.message.answer_media_group(
                        media=[
                            types.InputMediaPhoto(
                                media=types.FSInputFile(
                                    path=resources.files('vk_to_commerceml.data').joinpath('import_csv_01.png')),
                            ),
                            types.InputMediaPhoto(
                                media=types.FSInputFile(
                                    path=resources.files('vk_to_commerceml.data').joinpath('import_csv_02.png')),
                            ),
                            types.InputMediaPhoto(
                                media=types.FSInputFile(
                                    path=resources.files('vk_to_commerceml.data').joinpath('import_csv_03.png')),
                                caption=caption,
                            ),
                        ],
                    )
                    await query.message.answer_document(csv_file)
                case SyncState.MAIN_FAILED:
                    await query.message.answer(f'Ошибка отправки товаров на сайт: {content}')
                case SyncState.PHOTO_SUCCESS:
                    await query.message.answer(f'Успешно отправлено {content} фото на сайт')
                case SyncState.PHOTO_FAILED:
                    await query.message.answer(f'Ошибка отправки фото на сайт: {content}')

    except Exception as exc:
        await query.message.answer(f'Непредвиденная ошибка: {exc}')
        return
    await query.message.answer(f'Синхронизация завершена за {datetime.now() - started_at}')


async def get_sync_markup(state: FSMContext, callback_data: SyncCallback) -> types.InlineKeyboardMarkup:
    await state.update_data(sync=callback_data.model_dump_json(exclude={'start'}))
    builder = InlineKeyboardBuilder()
    builder.button(
        text=('☑' if callback_data.with_disabled else '☐') + '  получать скрытые в ВК',
        callback_data=callback_data.model_copy(update={'with_disabled': not callback_data.with_disabled}),
    )
    builder.button(
        text=('☑' if callback_data.with_photos else '☐') + '  синхронизировать фото',
        callback_data=callback_data.model_copy(update={'with_photos': not callback_data.with_photos}),
    )
    builder.button(
        text='🚀 запуск',
        callback_data=callback_data.model_copy(update={'start': True}),
    )
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(Form.authorized, SyncCallback.filter())
async def callback_config_sync(query: types.CallbackQuery, callback_data: SyncCallback, state: FSMContext) -> None:
    await query.message.edit_reply_markup(reply_markup=await get_sync_markup(state, callback_data))
    await query.answer('Настройка изменена')


@router.message(Form.authorized, Command('sync'))
async def command_sync(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get('sync'):
        callback_data = SyncCallback.model_validate_json(data['sync'])
    else:
        callback_data = SyncCallback()
    await message.answer(
        text='Настрой синхронизацию и запусти',
        reply_markup=await get_sync_markup(state, callback_data),
    )


@router.message(Command('logout'))
async def command_sync(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer('Авторизация в ВК удалена')


@router.message(CommandStart(deep_link=True))
async def command_start_unauthorized_handler(message: types.Message, command: CommandObject) -> None:
    if command.args == 'auth_fail':
        await message.answer('Ошибка авторизации.')


@router.message(Form.authorized)
async def default_authorized_handler(message: types.Message) -> None:
    await message.answer('Для запуска синхронизации используй команду /sync')


@router.message()
async def default_handler(message: types.Message, state: FSMContext) -> None:
    state_code = token_urlsafe()
    app_state.oauth_request_state_keys[state_code] = state.key
    url = URL(OAUTH_URL).with_query({
        'client_id': settings.vk.client_id,
        'display': 'mobile',
        'redirect_uri': str(settings.vk.oauth_callback_url),
        'scope': 'offline,market',
        'response_type': 'code',
        'state': state_code,
        'v': '5.199',
    })
    await message.answer(
        f'Привет, {hbold(message.from_user.full_name)}! Боту нужен доступ к товарам ВК.',
        parse_mode='HTML',
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
            types.InlineKeyboardButton(text='Авторизоваться в ВК', url=str(url)),
        ]])
    )


async def set_bot_commands_menu(my_bot: Bot) -> None:
    # Register commands for Telegram bot (menu)
    commands = [
        types.BotCommand(command="/sync", description='Запуск синхронизации'),
        types.BotCommand(command="/logout", description='Отменить авторизацию на ВК'),
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
    dp.include_router(router)
    task = asyncio.create_task(dp._polling(bot, allowed_updates=['message', 'callback_query', 'inline_query']))


async def stop_telegram() -> None:
    task.cancel()
