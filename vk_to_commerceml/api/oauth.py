from aiogram.fsm.context import FSMContext
from aiogram.utils.link import create_telegram_link
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from vk_to_commerceml.app_state import app_state
from vk_to_commerceml.bot.connect import select_vk_group
from vk_to_commerceml.bot.main import bot
from vk_to_commerceml.bot.states import Form
from vk_to_commerceml.settings import settings

router = APIRouter(
    prefix='/oauth',
    tags=['oauth'],
)


@router.get('/callback', status_code=303)
async def oauth_callback(code: str = Query(), state: str = Query()) -> RedirectResponse:
    bot_info = await bot.me()
    assert bot_info.username
    if state not in app_state.oauth_request_state_keys:
        return RedirectResponse(url=create_telegram_link(bot_info.username, start='auth_fail'), status_code=303)
    key = app_state.oauth_request_state_keys[state]
    access_token = await app_state.vk_client.get_access_token(
        settings.vk.client_id, settings.vk.client_secret,
        redirect_uri=str(settings.vk.oauth_callback_url),
        code=code,
    )
    await app_state.bot_storage.update_data(key, {'vk_token': access_token})
    await app_state.bot_storage.set_state(key, Form.vk_authorized)

    message = await bot.send_message(
        key.chat_id, 'Авторизация в ВК прошла успешно.'
    )
    await select_vk_group(message=message, state=FSMContext(app_state.bot_storage, key))
    return RedirectResponse(url=create_telegram_link(bot_info.username), status_code=303)
