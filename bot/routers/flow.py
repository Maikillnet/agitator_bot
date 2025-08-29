# bot/routers/flow.py
from __future__ import annotations

import re
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import Message
from sqlalchemy import select

from ..states import Survey  # убедись, что в states есть перечисленные ниже состояния
from ..db import async_session
from ..repo import (
    get_or_create_agent, create_visit, close_visit, create_contact,
    update_contact_fields, close_contact, flyer_exists,
)
from ..models import RepeatTouch, TalkStatus, FlyerMethod, Contact
from ..utils.phone import normalize_phone
from ..utils.webhook import send_lottery_code

from ..keyboards import (
    remove, kb_main, kb_cancel, kb_finish_or_add,
    kb_repeat_touch, kb_status, kb_flyer_method, kb_yes_no,
    BTN_NEW, BTN_CANCEL, BTN_FINISH, BTN_ADD_MORE, BTN_MAIN_MENU,
    BTN_PRIMARY, BTN_SECONDARY,
    BTN_NO_ONE, BTN_REFUSAL, BTN_CONSENT,
    BTN_HAND, BTN_MAILBOX, BTN_NO,
    BTN_YES, BTN_NOT,
)

router = Router(name="flow")


# ===== вспомогательная клавиатура главного меню для пользователя
async def _main_kb_for(user_id: int):
    async with async_session() as session:
        agent = await get_or_create_agent(session, user_id)
        await session.commit()
        is_admin = bool(getattr(agent, "admin_logged_in", False))
    return kb_main(is_admin=is_admin)


# ===== отмена запрещена на критичных шагах
STRICT_STATES = (
    Survey.waiting_photo_door,
    Survey.waiting_mailbox_photo,
    Survey.waiting_flyer_number,
)

@router.message(StateFilter(*STRICT_STATES), F.text == BTN_CANCEL)
async def deny_cancel_on_strict_steps(m: Message, state: FSMContext):
    await m.answer("❗️На этом шаге отмена недоступна. Выполните требуемое действие.")


@router.message(F.text == BTN_CANCEL)
async def on_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Окей, прервал. Что дальше?", reply_markup=await _main_kb_for(m.from_user.id))


# ===== старт опроса
@router.message(F.text == BTN_NEW)
async def start_visit(m: Message, state: FSMContext):
    display_name = " ".join(filter(None, [m.from_user.first_name, m.from_user.last_name])).strip() or None
    username = m.from_user.username or None
    async with async_session() as session:
        agent = await get_or_create_agent(session, m.from_user.id, name=display_name, username=username)
        visit = await create_visit(session, agent_id=agent.id)
        await session.commit()
    await state.update_data(visit_id=visit.id, agent_id=agent.id, additional=False)

    await m.answer("📷 Пришлите фото у двери квартиры (обязательно).", reply_markup=remove())
    await state.set_state(Survey.waiting_photo_door)


# ===== фото у двери
@router.message(Survey.waiting_photo_door, F.photo)
async def door_photo(m: Message, state: FSMContext):
    # если хотите хранить сам факт фото — можно проставить флаг у визита/контакта
    await m.answer("✍️ Введите ФИО избирателя полностью (пример: Иванов Иван Иванович).", reply_markup=kb_cancel())
    await state.set_state(Survey.waiting_full_name)


@router.message(Survey.waiting_photo_door)
async def door_photo_required(m: Message, state: FSMContext):
    # принимать документ-картинку как фото
    if m.document and (m.document.mime_type or "").startswith("image/"):
        await m.answer("✍️ Введите ФИО полностью (пример: Иванов Иван Иванович).", reply_markup=kb_cancel())
        await state.set_state(Survey.waiting_full_name)
        return
    await m.answer("📸 Жду фото у двери — это обязательный шаг.")


# ===== ФИО
@router.message(Survey.waiting_full_name, F.text)
async def get_full_name(m: Message, state: FSMContext):
    raw = (m.text or "").strip()
    parts = [p for p in re.split(r"\s+", raw) if p]

    def _is_cyr_word(w: str) -> bool:
        return re.fullmatch(r"[А-Яа-яЁё-]+", w) is not None

    if len(parts) != 3 or not all(_is_cyr_word(p) for p in parts):
        await m.answer("⚠️ Укажите ФИО избирателя полностью: фамилия, имя, отчество.", reply_markup=kb_cancel())
        return

    def _cap(s: str) -> str:
        return "-".join([w.capitalize() for w in s.split("-")])

    fam, nam, otc = (_cap(parts[0]), _cap(parts[1]), _cap(parts[2]))
    full_name = f"{fam} {nam} {otc}"

    await state.update_data(full_name=full_name)
    await m.answer("📞 Введите телефон избирателя в формате +7XXXXXXXXXX (ровно 11 цифр).", reply_markup=kb_cancel())
    await m.answer("Подсказка: +79991234567")
    await state.set_state(Survey.waiting_phone)


# ===== телефон (текстом или контактом)
@router.message(Survey.waiting_phone, F.contact)
async def get_phone_contact(m: Message, state: FSMContext):
    phone = normalize_phone(m.contact.phone_number)
    if not phone:
        await m.answer("⚠️ Не смог разобрать номер избирателя из контакта. Введите вручную: +7XXXXXXXXXX.")
        return
    await _commit_phone_and_open_next_steps(m, state, phone)


@router.message(Survey.waiting_phone)
async def get_phone(m: Message, state: FSMContext):
    phone = normalize_phone(m.text)
    if not phone:
        await m.answer("❌ Введите номер избирателя в формате +7XXXXXXXXXX")
        return
    await _commit_phone_and_open_next_steps(m, state, phone)


async def _commit_phone_and_open_next_steps(m: Message, state: FSMContext, phone: str):
    data = await state.get_data()
    visit_id = data["visit_id"]
    agent_id = data["agent_id"]
    full_name = data["full_name"]

    async with async_session() as session:
        contact = await create_contact(
            session,
            visit_id=visit_id,
            agent_id=agent_id,
            full_name=full_name,
            phone_e164=phone,
        )
        # фиксируем, что фото у двери было
        await update_contact_fields(session, contact.id, door_photo=True)
        await session.commit()

    await state.update_data(contact_id=contact.id, phone=phone)

    if data.get("additional"):
        await m.answer("🎟 Выдача флаера: как передали?", reply_markup=kb_flyer_method())
        await state.set_state(Survey.waiting_flyer_method)
    else:
        await m.answer("🔁 Повторность касания: выберите вариант.", reply_markup=kb_repeat_touch())
        await state.set_state(Survey.waiting_repeat_touch)


# ===== повторность касания
@router.message(Survey.waiting_repeat_touch, F.text.in_([BTN_PRIMARY, BTN_SECONDARY]))
async def choose_repeat(m: Message, state: FSMContext):
    val = RepeatTouch.PRIMARY if m.text == BTN_PRIMARY else RepeatTouch.SECONDARY
    data = await state.get_data()
    contact_id = data["contact_id"]
    async with async_session() as session:
        await update_contact_fields(session, contact_id, repeat_touch=val)
        await session.commit()
    await m.answer("🗣 Статус общения: как прошло?", reply_markup=kb_status())
    await state.set_state(Survey.waiting_talk_status)


# ===== статус общения
@router.message(Survey.waiting_talk_status, F.text.in_([BTN_NO_ONE, BTN_REFUSAL, BTN_CONSENT]))
async def choose_talk_status(m: Message, state: FSMContext):
    mapping = {
        BTN_NO_ONE: TalkStatus.NO_ONE,
        BTN_REFUSAL: TalkStatus.REFUSAL,
        BTN_CONSENT: TalkStatus.CONSENT,
    }
    status = mapping[m.text]
    data = await state.get_data()
    contact_id = data["contact_id"]

    async with async_session() as session:
        await update_contact_fields(session, contact_id, talk_status=status)
        await session.commit()

    if status == TalkStatus.NO_ONE:
        # первичка + никого нет → закрываем карточку
        async with async_session() as session:
            res = await session.execute(select(Contact).where(Contact.id == contact_id))
            c = res.scalars().first()
            if c and c.repeat_touch == RepeatTouch.PRIMARY:
                await close_contact(session, contact_id)
                await session.commit()
                await state.update_data(last_closed_contact_id=contact_id)
                await m.answer("Никого нет (первичный обход). Карточка закрыта. Что дальше?", reply_markup=kb_finish_or_add())
                await state.set_state(Survey.waiting_finish_choice)
                return

        # иначе продолжаем
        await m.answer("Никого нет (вторичный обход). 🎟 Выдача флаера: как передали?", reply_markup=kb_flyer_method())
        await state.set_state(Survey.waiting_flyer_method)
        return

    await m.answer("🎟 Выдача флаера: как передали?", reply_markup=kb_flyer_method())
    await state.set_state(Survey.waiting_flyer_method)


@router.message(Survey.waiting_flyer_method, F.text.in_([BTN_HAND, BTN_MAILBOX, BTN_NO]))
async def choose_flyer(m: Message, state: FSMContext):
    mapping = {
        BTN_HAND:    FlyerMethod.HAND,
        BTN_MAILBOX: FlyerMethod.MAILBOX,
        BTN_NO:      FlyerMethod.NONE,
    }
    method = mapping[m.text]

    data = await state.get_data()
    contact_id = data["contact_id"]

    # Сохраняем метод выдачи
    async with async_session() as session:
        await update_contact_fields(session, contact_id, flyer_method=method)
        await session.commit()

    # ❗ И "На руки", и "В ящик" → просим номер флаера (обязательно)
    if method in (FlyerMethod.HAND, FlyerMethod.MAILBOX):
        await prompt_flyer_number(m, state)
        return

    # 🚫 Не выдавали → сразу к вопросу про голосование на дому
    await m.answer("🏠 Голосование на дому: требуется ли урна?", reply_markup=kb_yes_no())
    await state.set_state(Survey.waiting_home_voting)

# --- ПОДСказка для номера флаера ---
async def prompt_flyer_number(m: Message, state: FSMContext):
    await m.answer("🔢 Введите номер флаера (обязательно). Только цифры от 1 до 60 000.", reply_markup=remove())
    await state.set_state(Survey.waiting_flyer_number)


# --- Ввод номера флаера ---
@router.message(Survey.waiting_flyer_number, F.text)
async def flyer_number_input(m: Message, state: FSMContext):
    text = (m.text or "").strip()
    if not text.isdigit():
        await m.answer("⚠️ Только цифры. Введите число от от 1 до 60 000.")
        return

    num = int(text)
    if not (1 <= num <= 60_000):
        await m.answer("⚠️ Номер вне диапазона. Допустимо от 1 до 60 000.")
        return

    # уникальность
    async with async_session() as session:
        if await flyer_exists(session, num):
            await m.answer("⚠️ Такой номер флаера уже использовался. Укажите другой.")
            return

    data = await state.get_data()
    contact_id = data["contact_id"]

    async with async_session() as session:
        await update_contact_fields(session, contact_id, flyer_number=str(num))
        await session.commit()

    # сохраним код в FSM, чтобы вебхук гарантированно его получил
    await state.update_data(lottery_code=str(num))

    await m.answer("🏠 Голосование на дому: требуется ли урна?", reply_markup=kb_yes_no())
    await state.set_state(Survey.waiting_home_voting)


@router.message(Survey.waiting_flyer_number)
async def flyer_number_required(m: Message, state: FSMContext):
    await m.answer("#️⃣ Номер флаера обязателен. Введите, пожалуйста.")


# --- Голосование на дому + вызов вебхука ---
@router.message(Survey.waiting_home_voting, F.text.in_([BTN_YES, BTN_NOT]))
async def home_voting(m: Message, state: FSMContext):
    voting_at_home = (m.text == BTN_YES)
    await state.update_data(voting_at_home=voting_at_home)

    data = await state.get_data()
    phone_raw = data.get("phone")
    code = data.get("lottery_code")
    cid = data.get("contact_id")

    # если чего-то нет в состоянии — добираем из БД
    if (not phone_raw or not code) and cid:
        async with async_session() as session:
            c = await session.get(Contact, cid)
            if c:
                phone_raw = phone_raw or c.phone_e164
                code = code or (c.flyer_number or "")

    # отправляем вебхук (защита от двойного клика)
    if phone_raw and code and not data.get("wh_sent"):
        await state.update_data(wh_sent=True)
        ok, msg = await send_lottery_code(phone_raw, code, voting_at_home)
        if ok:
            await m.answer("✅ Спасибо! Данные сохранены.")
        else:
            await m.answer(f"⚠️ Не удалось сохранить данные, попробуйте позже. {msg}")

    # записываем home_voting и закрываем контакт
    if cid:
        async with async_session() as session:
            await update_contact_fields(session, cid, home_voting=voting_at_home)
            await close_contact(session, cid)
            await session.commit()
        await state.update_data(last_closed_contact_id=cid)

    await m.answer("✅ Карточка готова. Завершить обход или добавить ещё избирателя?",
                   reply_markup=kb_finish_or_add())
    await state.set_state(Survey.waiting_finish_choice)

# ===== завершение квартиры / добавить ещё
@router.message(Survey.waiting_finish_choice, F.text.in_([BTN_FINISH, BTN_ADD_MORE, BTN_MAIN_MENU]))
async def finish_choice(m: Message, state: FSMContext):
    data = await state.get_data()
    visit_id = data.get("visit_id")

    if m.text == BTN_FINISH:
        async with async_session() as session:
            await close_visit(session, visit_id)
            await session.commit()
        await state.clear()
        await m.answer("Опрос завершён. Что дальше?", reply_markup=await _main_kb_for(m.from_user.id))
        return

    if m.text == BTN_ADD_MORE:
        await state.update_data(additional=True,  # пометим, что следующий — «дополнительный»
                               phone=None, lottery_code=None, wh_sent=False)
        await m.answer("✍️ Введите ФИО избирателя полностью (пример: Иванов Иван Иванович).", reply_markup=kb_cancel())
        await state.set_state(Survey.waiting_full_name)
        return

    # BTN_MAIN_MENU
    await state.clear()
    await m.answer("Главное меню:", reply_markup=await _main_kb_for(m.from_user.id))
