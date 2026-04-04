from typing import Annotated

from aiogram.fsm.context import FSMContext
from aiogram.utils.link import create_telegram_link
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from vk_to_commerceml.app_state import app_state
from vk_to_commerceml.bot.connect import select_vk_group
from vk_to_commerceml.bot.main import bot
from vk_to_commerceml.bot.states import Form
from vk_to_commerceml.infrastructure.vk.oauth import get_authorization_url
from vk_to_commerceml.settings import settings

router = APIRouter(
    prefix='/oauth',
    tags=['oauth'],
)


@router.get('/callback', status_code=303)
async def oauth_callback(
    code: Annotated[str, Query()], state: Annotated[str, Query()], device_id: Annotated[str, Query()]
) -> RedirectResponse:
    bot_info = await bot.me()
    assert bot_info.username
    if state not in app_state.oauth_request_state_keys:
        return RedirectResponse(url=create_telegram_link(bot_info.username, start='auth_fail'), status_code=303)
    key = app_state.oauth_request_state_keys.pop(state)
    bot_state = await app_state.bot_storage.get_state(key)
    verifier = await app_state.bot_storage.get_value(key, 'vk_oauth_verifier')
    if not verifier:
        return RedirectResponse(url=create_telegram_link(bot_info.username, start='auth_fail'), status_code=303)
    if bot_state == Form.vk_start:
        access_token = await app_state.vk_client.get_access_token(
            settings.vk.client_id, settings.vk.client_secret,
            redirect_uri=str(settings.vk.oauth_callback_url),
            code=code,
            verifier=verifier,
            device_id=device_id,
            state=state,
        )
        await app_state.bot_storage.update_data(key, {'vk_token': app_state.secrets.encrypt(access_token)})
        await app_state.bot_storage.set_state(key, Form.vk_authorized)

        message = await bot.send_message(
            key.chat_id, 'Авторизация в ВК прошла успешно.'
        )
        await select_vk_group(message=message, state=FSMContext(app_state.bot_storage, key))
    else:
        await bot.send_message(
            key.chat_id, 'Вы уже авторизованы в ВК.'
        )
    return RedirectResponse(url=create_telegram_link(bot_info.username), status_code=303)


@router.get('/redirect/{state}', status_code=303)
async def redirect(state: str) -> RedirectResponse:
    bot_info = await bot.me()
    assert bot_info.username
    if state not in app_state.oauth_request_state_keys:
        return RedirectResponse(url=create_telegram_link(bot_info.username, start='auth_fail'), status_code=303)
    key = app_state.oauth_request_state_keys[state]
    bot_state = await app_state.bot_storage.get_state(key)
    if bot_state == Form.vk_start:
        url, verifier = get_authorization_url(settings.vk.client_id, str(settings.vk.oauth_callback_url), state)
        await app_state.bot_storage.update_data(key, {'vk_oauth_verifier': verifier})
        return RedirectResponse(
            url=url,
            status_code=303,
        )
    else:
        del app_state.oauth_request_state_keys[state]
        return RedirectResponse(url=create_telegram_link(bot_info.username), status_code=303)
