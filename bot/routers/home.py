# bot/routers/home.py
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from ..db import async_session
from ..repo import (
    is_member_blocked,
    get_or_create_agent,
    is_brig_logged_in,
    set_brig_login,
    is_brigadier_allowed,
)
from ..keyboards import (
    BTN_ACCESS, BTN_ADMIN, BTN_ADMIN_LOGIN,
    BTN_BRIG_LOGIN, BTN_BRIG_LOGOUT, BTN_BRIG_MENU, BTN_BACK, BTN_HELP,
    kb_access_menu, kb_admin_menu, kb_brig_menu, kb_main,
)

router = Router(name="home")

async def _is_admin_logged(user_id: int) -> bool:
    # если у Agent нет такого поля — всегда False (getattr)
    async with async_session() as session:
        agent = await get_or_create_agent(session, user_id)
        await session.commit()
        return bool(getattr(agent, "admin_logged_in", False))

async def _is_brig_logged(user_id: int) -> bool:
    async with async_session() as session:
        return await is_brig_logged_in(session, user_id)

@router.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    # регистрируем/обновляем агента
    async with async_session() as session:
        await get_or_create_agent(
            session,
            m.from_user.id,
            name=m.from_user.full_name,
            username=m.from_user.username,
        )
        await session.commit()
    # блокировки
    async with async_session() as s2:
        if await is_member_blocked(s2, m.from_user.id):
            await m.answer('⛔️ Доступ к опросам ограничен администратором/бригадиром.')
            return
    admin_ok = await _is_admin_logged(m.from_user.id)
    brig_ok = await _is_brig_logged(m.from_user.id)
    await m.answer(
        "Привет! Я на связи. Выбирай действие:",
        reply_markup=kb_main(is_admin=admin_ok, is_brig=brig_ok),
    )

@router.message(F.text == BTN_ACCESS)
async def access_menu(m: Message):
    admin_ok = await _is_admin_logged(m.from_user.id)
    brig_ok = await _is_brig_logged(m.from_user.id)
    await m.answer(
        "Выберите раздел доступа:",
        reply_markup=kb_access_menu(brig_logged=brig_ok, admin_logged=admin_ok),
    )

@router.message(F.text == BTN_BRIG_LOGIN)
async def brig_login(m: Message):
    async with async_session() as session:
        if not await is_brigadier_allowed(session, m.from_user.id):
            await m.answer("Вас ещё не назначили бригадиром. Сначала админ должен добавить вас в список.")
            return
        await set_brig_login(session, m.from_user.id, True)
        await session.commit()
    await m.answer("✅ Вход как бригадир выполнен.", reply_markup=kb_brig_menu())

@router.message(F.text == BTN_BRIG_LOGOUT)
async def brig_logout(m: Message):
    async with async_session() as session:
        await set_brig_login(session, m.from_user.id, False)
        await session.commit()
    # блокировки
    async with async_session() as s2:
        if await is_member_blocked(s2, m.from_user.id):
            await m.answer('⛔️ Доступ к опросам ограничен администратором/бригадиром.')
            return
    admin_ok = await _is_admin_logged(m.from_user.id)
    await m.answer(
        "Вы вышли из бригадирского режима.",
        reply_markup=kb_access_menu(brig_logged=False, admin_logged=admin_ok),
    )

@router.message(F.text == BTN_BRIG_MENU)
async def open_brig_menu(m: Message):
    brig_ok = await _is_brig_logged(m.from_user.id)
    if not brig_ok:
        await m.answer(
            "Сначала войдите как бригадир.",
            reply_markup=kb_access_menu(brig_logged=False, admin_logged=await _is_admin_logged(m.from_user.id)),
        )
        return
    await m.answer("🪖 Бригадир-меню", reply_markup=kb_brig_menu())

@router.message(F.text == BTN_HELP)
async def on_help(m: Message):
    admin_ok = await _is_admin_logged(m.from_user.id)
    brig_ok = await _is_brig_logged(m.from_user.id)
    text = (
        "ℹ️ <b>Помощь</b>\n"
        "— «Новый опрос» — запуск сценария обхода квартир.\n"
        "— «Сводка за смену» — ваши цифры за 24 часа.\n"
        "— «Доступ» — вход в Админ-меню и Бригадир-режим.\n"
        "Если что-то не работает — просто нажмите «/start»."
    )
    await m.answer(text, reply_markup=kb_main(is_admin=admin_ok, is_brig=brig_ok))

@router.message(F.text == BTN_BACK)
async def back_to_main(m: Message, state: FSMContext):
    await state.clear()
    admin_ok = await _is_admin_logged(m.from_user.id)
    brig_ok = await _is_brig_logged(m.from_user.id)
    await m.answer("Главное меню.", reply_markup=kb_main(is_admin=admin_ok, is_brig=brig_ok))
