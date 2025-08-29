from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# ========== Общие ==========
BTN_CANCEL = "✖️ Отмена"
BTN_BACK = "⬅️ Назад"
BTN_MAIN_MENU = "🏠 В главное меню"

def remove() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()

# ========== Главное меню агента ==========
BTN_NEW = "▶️ Новый опрос (квартира)"
BTN_HELP = "ℹ️ Помощь"
BTN_MY_STATS = "📊 Сводка за смену"
BTN_AGENT_EXPORT_XLSX = "📥 Моя выгрузка (XLSX)"
BTN_ACCESS = "🔑 Доступ"  # вход в админ/бригадирские разделы

def kb_main(is_admin: bool = False, is_brig: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_NEW)],
        [KeyboardButton(text=BTN_MY_STATS), KeyboardButton(text=BTN_HELP)],
        [KeyboardButton(text=BTN_AGENT_EXPORT_XLSX)], 
        [KeyboardButton(text=BTN_ACCESS)],
    ]
    # В главном меню лишних пунктов не показываем
    # Админ-меню и Бригадир-меню доступны из раздела "Доступ"
    if is_admin:
        rows.append([KeyboardButton(text=BTN_ADMIN)])
    if is_brig:
        rows.append([KeyboardButton(text=BTN_BRIG_MENU)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

# ========== Доступ/логины ==========
BTN_ADMIN = "🛠 Админ-меню"
BTN_ADMIN_LOGIN = "🔐 Админ-вход"
BTN_ADMIN_LOGOUT = "🚪 Выйти из админа"

BTN_BRIG_MENU = "🪖 Бригадир-меню"
BTN_BRIG_LOGIN = "🧑‍✈️ Вход бригадира"
BTN_BRIG_LOGOUT = "🚪 Выйти из бригадира"

def kb_access_menu(*, brig_logged: bool, admin_logged: bool) -> ReplyKeyboardMarkup:
    rows = []
    # Админ
    rows.append([KeyboardButton(text=BTN_ADMIN if admin_logged else BTN_ADMIN_LOGIN)])
    # Бригадир
    if brig_logged:
        rows.append([KeyboardButton(text=BTN_BRIG_MENU), KeyboardButton(text=BTN_BRIG_LOGOUT)])
    else:
        rows.append([KeyboardButton(text=BTN_BRIG_LOGIN)])
    rows.append([KeyboardButton(text=BTN_BACK)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def kb_cancel() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True
    )

# ========== Повторность касания ==========
BTN_PRIMARY = "🔁 Первичное касание"
BTN_SECONDARY = "🔁 Повторное касание"

def kb_repeat_touch() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_PRIMARY)],
            [KeyboardButton(text=BTN_SECONDARY)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True
    )

# ========== Статус общения ==========
BTN_NO_ONE   = "🚪 Никого нет"
BTN_REFUSAL  = "🙅 Отказ от общения"
BTN_CONSENT  = "✅ Получено согласие"

def kb_status() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CONSENT)],   # ↑ всегда сверху
            [KeyboardButton(text=BTN_REFUSAL)],
            [KeyboardButton(text=BTN_NO_ONE)],    # ↓ всегда внизу среди вариантов
            [KeyboardButton(text=BTN_CANCEL)],    # служебная кнопка последней строкой
        ],
        resize_keyboard=True
    )

# ========== Флаер ==========
BTN_HAND = "🖐️ Флаер — на руки"
BTN_MAILBOX = "📮 Флаер — в почтовый ящик"
BTN_NO = "🚫 Нет"

def kb_flyer_method() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_HAND)],
            [KeyboardButton(text=BTN_MAILBOX)],
            [KeyboardButton(text=BTN_NO)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True
    )

# ========== Да/Нет (голосование на дому) ==========
BTN_YES = "🏠 Голосование на дому — Да"
BTN_NOT = "🏠 Голосование на дому — Нет"

def kb_yes_no() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_YES)],
            [KeyboardButton(text=BTN_NOT)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True
    )

# ========== Пропуск / Завершение ==========
BTN_SKIP = "Пропустить"
BTN_FINISH = "✅ Завершить опрос"
BTN_ADD_MORE = "➕ Добавить ещё избирателя в этой квартире"

def kb_skip_or_cancel() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SKIP)], [KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True
    )

def kb_finish_or_add() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_FINISH)],
            [KeyboardButton(text=BTN_ADD_MORE)],
            [KeyboardButton(text=BTN_MAIN_MENU)],  # выход в главное меню после завершения квартиры
        ],
        resize_keyboard=True
    )

# ========== Админ ==========
BTN_ADMIN_HELP = "ℹ️ Справка админа"
BTN_ADMIN_STATS_ALL = "📈 Сводка по всем"
BTN_ADMIN_EXPORT_XLSX = "📤 Экспорт XLSX"
BTN_ADMIN_EXPORT_CSV = "📩 Экспорт CSV"
BTN_XLSX_ALL = "XLSX — всё"
BTN_CSV_ALL = "CSV — всё"

# --- Доступы (бригадиры) ---
BTN_ADMIN_ACCESS         = "🔑 Доступы (бригадиры)"
BTN_ACCESS_ADD_BRIG      = "➕ Назначить бригадира"
BTN_ACCESS_ATTACH_MEMBER = "👥 Привязать участника к бригадиру"
BTN_ACCESS_LIST          = "📋 Список бригадиров"
BTN_ACCESS_DEMOTE        = "⛔️ Разжаловать бригадира"
BTN_BRIG_HELP            = "ℹ️ Помощь"

def kb_admin_menu() -> ReplyKeyboardMarkup:
    # вертикально, чтобы было читаемо
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text=BTN_ADMIN_ACCESS)],
            [KeyboardButton(text=BTN_ADMIN_STATS_ALL)],
            [KeyboardButton(text=BTN_ADMIN_EXPORT_XLSX)],
            [KeyboardButton(text=BTN_ADMIN_EXPORT_CSV)],
            [KeyboardButton(text=BTN_BRIG_HELP)],
            [KeyboardButton(text=BTN_ADMIN_LOGOUT)],
            [KeyboardButton(text=BTN_BACK)],
        ],
    )

# АКТУАЛЬНОЕ подменю «Доступы (бригадиры)» — с разжалованием
def kb_admin_access_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text=BTN_ACCESS_ADD_BRIG)],
            [KeyboardButton(text=BTN_ACCESS_ATTACH_MEMBER)],
            [KeyboardButton(text=BTN_ACCESS_LIST)],
            [KeyboardButton(text=BTN_ACCESS_DEMOTE)],  # ⛔️ Разжаловать
            [KeyboardButton(text=BTN_BACK)],
        ],
    )

def kb_admin_export_xlsx() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text=BTN_XLSX_ALL)],
            [KeyboardButton(text=BTN_BACK)],
        ],
    )

def kb_admin_export_csv() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text=BTN_CSV_ALL)],
            [KeyboardButton(text=BTN_BACK)],
        ],
    )

def kb_share_contact() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер", request_contact=True)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True
    )

def kb_export_ranges() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_EXP_TODAY), KeyboardButton(text=BTN_EXP_7)],
            [KeyboardButton(text=BTN_EXP_30), KeyboardButton(text=BTN_EXP_ALL)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True
    )

# ========== Периоды экспорта ==========
BTN_EXP_TODAY = "📅 Сегодня"
BTN_EXP_7 = "🗓 Последние 7 дней"
BTN_EXP_30 = "🗓 Последние 30 дней"
BTN_EXP_ALL = "🗃 Весь период"

# ========== Бригадирское меню (на будущее/совместимость) ==========
BTN_BRIG_MEMBERS      = "👥 Участники"
BTN_BRIG_ATTACH       = "🔗 Привязать участника"
BTN_BRIG_DETACH       = "🧹 Отвязать участника"
BTN_BRIG_BLACKLIST    = "🧱 Чёрный список"
BTN_BRIG_BLOCK        = "🚫 Заблокировать участника"
BTN_BRIG_UNBLOCK      = "♻️ Разблокировать участника"
BTN_BRIG_STATS        = "📈 Сводка по участникам"
BTN_BRIG_EXPORT_XLSX  = "📦 Экспорт XLSX (бригада)"
BTN_BRIG_HELP         = "ℹ️ Помощь (бригадир)"

def kb_brig_blacklist() -> ReplyKeyboardMarkup:
    # подменю: вертикально
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_BRIG_BLOCK)],
            [KeyboardButton(text=BTN_BRIG_UNBLOCK)],
            [KeyboardButton(text=BTN_BRIG_MENU)],  # назад в меню бригадира
        ],
        resize_keyboard=True
    )

def kb_brig_menu() -> ReplyKeyboardMarkup:
    # основное меню бригадира (вертикально, как просил)
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_BRIG_MEMBERS)],
            [KeyboardButton(text=BTN_BRIG_ATTACH), KeyboardButton(text=BTN_BRIG_DETACH)],
            [KeyboardButton(text=BTN_BRIG_BLACKLIST)],   # подменю «Чёрный список»
            [KeyboardButton(text=BTN_BRIG_EXPORT_XLSX)],
            [KeyboardButton(text=BTN_BRIG_LOGOUT)],
            [KeyboardButton(text=BTN_BACK)],
            [KeyboardButton(text=BTN_BRIG_HELP)],
        ],
        resize_keyboard=True
    )



