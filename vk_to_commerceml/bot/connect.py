from secrets import token_urlsafe

from aiogram import Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hbold
from pydantic import SecretStr
from yarl import URL

from vk_to_commerceml.app_state import app_state
from vk_to_commerceml.bot.models import Site, SITE_DISPLAY_NAMES
from vk_to_commerceml.bot.states import Form
from vk_to_commerceml.infrastructure.vk.client import OAUTH_URL
from vk_to_commerceml.settings import settings

router = Router()


class VkGroupCallback(CallbackData, prefix='vk_group'):
    id: int


class SiteCallback(CallbackData, prefix='site'):
    name: Site


@router.message(Command('logout'))
async def command_logout(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer('Авторизация в ВК удалена')


@router.message(CommandStart(deep_link=True))
async def command_start_unauthorized_handler(message: types.Message, command: CommandObject) -> None:
    if command.args == 'auth_fail':
        await message.answer('Ошибка авторизации.')


@router.message(Form.cml_password_entered)
async def default_authorized_handler(message: types.Message) -> None:
    await message.answer('Для запуска синхронизации используй команду /sync')


@router.message(Form.cml_login_entered, F.text)
async def enter_cml_password(message: types.Message, state: FSMContext) -> None:
    if not message.text:
        return
    password = SecretStr(message.text.strip())
    await state.update_data(cml_password=app_state.secrets.encrypt(password))
    await state.set_state(Form.cml_password_entered)
    await message.delete()
    await message.answer('Пароль CommerceML сохранен')
    await message.answer('Настройка успешно завершена')
    await default_authorized_handler(message=message)


@router.message(Form.cml_login_entered)
async def prompt_cml_password(message: types.Message) -> None:
    await message.answer('Введите пароль CommerceML')


@router.message(Form.cml_site_selected, F.text)
async def enter_cml_login(message: types.Message, state: FSMContext) -> None:
    if not message.text:
        return
    login = message.text.strip()
    await state.update_data(cml_login=login)
    await state.set_state(Form.cml_login_entered)
    await message.delete()
    await message.answer(f'Имя пользователя CommerceML: `{login}`', parse_mode=ParseMode.MARKDOWN_V2)
    await prompt_cml_password(message=message)


@router.message(Form.cml_site_selected)
async def prompt_cml_login(message: types.Message) -> None:
    await message.answer('Введите имя пользователя CommerceML')


@router.callback_query(Form.vk_group_selected, SiteCallback.filter())
async def callback_site(query: types.CallbackQuery, callback_data: SiteCallback, state: FSMContext) -> None:
    await state.update_data(cml_site=callback_data.name)
    await state.set_state(Form.cml_site_selected)
    await query.answer('Сайт сохранен')
    await query.message.delete()
    await query.message.answer(
        f'Выбран сайт: `{SITE_DISPLAY_NAMES[callback_data.name]}`',
        parse_mode=ParseMode.MARKDOWN_V2
    )
    await prompt_cml_login(message=query.message)


@router.message(Form.vk_group_selected)
async def select_site(message: types.Message) -> None:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=SITE_DISPLAY_NAMES[Site.TILDA],
        callback_data=SiteCallback(name=Site.TILDA),
    )
    builder.adjust(1)
    await message.answer('Какой сайт вы хотите подключить?', reply_markup=builder.as_markup())


@router.callback_query(Form.vk_authorized, VkGroupCallback.filter())
async def callback_vk_group(query: types.CallbackQuery, callback_data: VkGroupCallback, state: FSMContext) -> None:
    data = await state.get_data()
    vk_token = app_state.secrets.decrypt(data['vk_token'])
    vk_client = await app_state.vk_client.get_session(vk_token)
    groups = await vk_client.get_groups()
    group = next(iter(group for group in groups if group.id == callback_data.id), None)
    if not group:
        await query.answer('Группа не найдена')
        return
    await state.update_data(vk_group_id=group.id)
    await state.set_state(Form.vk_group_selected)
    await query.answer('Группа сохранена')
    await query.message.delete()
    await query.message.answer(f'Выбрана группа: `{group.name}`', parse_mode=ParseMode.MARKDOWN_V2)
    await select_site(message=query.message)


@router.message(Form.vk_authorized)
async def select_vk_group(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    vk_token = app_state.secrets.decrypt(data['vk_token'])
    vk_client = await app_state.vk_client.get_session(vk_token)
    groups = await vk_client.get_groups()

    builder = InlineKeyboardBuilder()
    for group in groups:
        builder.button(
            text=group.name,
            callback_data=VkGroupCallback(id=group.id),
        )
    builder.adjust(1)
    await message.answer('Из какой группы вы хотите получать товары?', reply_markup=builder.as_markup())


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
