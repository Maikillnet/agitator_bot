from aiogram.fsm.state import StatesGroup, State

# -------- опрос --------
class Survey(StatesGroup):
    waiting_full_name = State()
    waiting_phone = State()
    waiting_repeat_touch = State()
    waiting_photo_door = State()
    waiting_talk_status = State()
    waiting_flyer_method = State()
    waiting_mailbox_photo = State()
    waiting_flyer_number = State()
    waiting_home_voting = State()
    waiting_finish_choice = State()

# -------- админ --------
class AdminExport(StatesGroup):
    waiting_range = State()

class AdminAuth(StatesGroup):
    waiting_login = State()
    waiting_password = State()

class AdminStats(StatesGroup):
    waiting_range = State()

# -------- доступы (бригадиры) --------
class AdminAccess(StatesGroup):
    # Назначение бригадира по @username
    waiting_brig_username = State()
    # Универсальное состояние для ввода участника в старых хендлерах
    waiting_member_username = State()
    # Отдельные состояния для флоу "Привязать участника к бригадиру",
    # чтобы не конфликтовать с назначением бригадира
    waiting_attach_brig_username = State()
    waiting_attach_member_username = State()
