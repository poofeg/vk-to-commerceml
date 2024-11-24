from aiogram.fsm.state import StatesGroup, State


class Form(StatesGroup):
    vk_start = State()
    vk_authorized = State()
    vk_group_selected = State()
    cml_site_selected = State()
    cml_url_entered = State()
    cml_login_entered = State()
    cml_password_entered = State()
