import logging
from datetime import datetime
from importlib import resources

from aiogram import F, types, Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from vk_to_commerceml.app_state import app_state
from vk_to_commerceml.bot.models import SITE_CATALOG_URLS, Site
from vk_to_commerceml.bot.states import Form
from vk_to_commerceml.services.sync import SyncService, SyncState

logger = logging.getLogger(__name__)
router = Router()


class SyncCallback(CallbackData, prefix='sync'):
    with_disabled: bool = False
    with_photos: bool = False
    start: bool = False


@router.callback_query(Form.cml_password_entered, SyncCallback.filter(F.start))
async def callback_sync(query: types.CallbackQuery, callback_data: SyncCallback, state: FSMContext) -> None:
    started_at = datetime.now()
    data = await state.get_data()
    vk_token = app_state.secrets.decrypt(data['vk_token'])
    vk_group_id: int = data['vk_group_id']
    cml_site: str = data['cml_site']
    cml_url: str = data['cml_url']
    cml_login: str = data['cml_login']
    cml_password = app_state.secrets.decrypt(data['cml_password'])
    await state.update_data(sync=callback_data.model_dump_json(exclude={'start'}))
    sync_service = SyncService(
        app_state.cml_client, cml_url, cml_login, cml_password,
        app_state.vk_client, vk_token, vk_group_id
    )
    await query.answer('Запуск синхронизации')
    await query.message.answer('Запуск синхронизации')
    try:
        async for status, content in sync_service.sync(
            callback_data.with_disabled, callback_data.with_photos,
            skip_multiple_group=cml_site == Site.TILDA,
            make_csv=cml_site == Site.TILDA,
        ):
            match status:
                case SyncState.GET_PRODUCTS_SUCCESS:
                    await query.message.answer(f'Из ВК успешно получено {content} товаров')
                case SyncState.GET_PRODUCTS_FAILED:
                    await query.message.answer(f'Ошибка получения товаров из ВК: {content}')
                case SyncState.MAIN_SUCCESS:
                    if content:
                        catalog_url = SITE_CATALOG_URLS[data['cml_site']].format(login=cml_login)
                        csv_file = types.BufferedInputFile(content.encode('utf8'), filename='categories.csv')
                        caption = 'Товары успешно отправлены на сайт. Чтобы проставить категорию новым товарам нужно ' \
                                  f'загрузить CSV-файл ниже на {catalog_url}, ' \
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
                    else:
                        await query.message.answer(f'Товары успешно отправлены на сайт')
                case SyncState.MAIN_FAILED:
                    await query.message.answer(f'Ошибка отправки товаров на сайт: {content}')
                case SyncState.PHOTO_SUCCESS:
                    await query.message.answer(f'Успешно отправлено {content} фото на сайт')
                case SyncState.PHOTO_FAILED:
                    await query.message.answer(f'Ошибка отправки фото на сайт: {content}')

    except Exception as exc:
        logger.exception('Unexpected sync error: %r', exc)
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


@router.callback_query(Form.cml_password_entered, SyncCallback.filter())
async def callback_config_sync(query: types.CallbackQuery, callback_data: SyncCallback, state: FSMContext) -> None:
    if isinstance(query.message, types.Message):
        await query.message.edit_reply_markup(reply_markup=await get_sync_markup(state, callback_data))
    await query.answer('Настройка изменена')


@router.message(Form.cml_password_entered, Command('sync'))
async def command_sync(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get('sync'):
        callback_data = SyncCallback.model_validate_json(data['sync'])
    else:
        callback_data = SyncCallback()
    await message.answer(
        text='Настройте синхронизацию и запустите',
        reply_markup=await get_sync_markup(state, callback_data),
    )
