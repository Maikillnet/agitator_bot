from __future__ import annotations

import logging
import html
from datetime import datetime
from pathlib import Path
import tempfile

from aiogram import Router, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from ..config import settings
from ..db import async_session
from ..repo import (
    # базовое
    list_contacts_for_period,
    get_or_create_agent,
    agents_stats_for_period,
    # бригадиры
    ensure_brig_tables,
    add_brigadier,
    set_brig_member,
    get_agent_by_username,   # ← добавили
    demote_brigadier, 
    list_brigadiers,
    resolve_username_to_tg,
)
from ..utils.excel import rows_to_dataframe, write_excel_with_pivot, write_admin_summary
from ..keyboards import (
    # меню/доступ
    BTN_ADMIN, BTN_ADMIN_LOGIN, BTN_ADMIN_LOGOUT, BTN_ADMIN_HELP, 
    BTN_ADMIN_STATS_ALL, BTN_ADMIN_ACCESS, BTN_ACCESS_DEMOTE,
    kb_admin_menu, kb_main, kb_admin_access_menu, kb_cancel, BTN_ADMIN_ACCESS, BTN_ACCESS_DEMOTE, BTN_BACK,

    # экспорт
    BTN_ADMIN_EXPORT_XLSX, BTN_ADMIN_EXPORT_CSV,
    BTN_XLSX_ALL, BTN_CSV_ALL,
    kb_admin_export_xlsx, kb_admin_export_csv,

    # периоды
    kb_export_ranges,
    BTN_EXP_TODAY, BTN_EXP_7, BTN_EXP_30, BTN_EXP_ALL, BTN_BACK,

    # доступы (кнопки подменю)
    BTN_ACCESS_ADD_BRIG, BTN_ACCESS_ATTACH_MEMBER, BTN_ACCESS_LIST,
)

from ..states import AdminAuth, AdminExport, AdminAccess
from sqlalchemy import select           # ← нужно для select(Agent)
from ..models import Agent              # ← чтобы select(Agent) работал

logger = logging.getLogger(__name__)
router = Router(name="admin")


# ----- STATES -----
class AdminStats(StatesGroup):
    waiting_range = State()

class AdminDemoteBrig(StatesGroup):
    waiting_username_or_id = State()

# ----- HELPERS -----
async def _is_admin_logged(user_id: int) -> bool:
    async with async_session() as session:
        agent = await get_or_create_agent(session, user_id)
        await session.commit()
        return bool(getattr(agent, "admin_logged_in", False))

@router.message(F.text == BTN_ACCESS_DEMOTE)
async def admin_access_demote_brig_start(m: Message, state: FSMContext):
    await state.set_state(AdminDemoteBrig.waiting_username_or_id)
    await m.answer(
        "Введите @username бригадира или его числовой Telegram ID, которого нужно разжаловать.",
        reply_markup=kb_cancel()
    )

# ===== AUTH / MENU =====
@router.message(F.text == BTN_ADMIN_LOGIN)
async def admin_login_start(m: Message, state: FSMContext):
    if await _is_admin_logged(m.from_user.id):
        await m.answer("Вы уже вошли как админ.", reply_markup=kb_admin_menu())
        return
    await m.answer("🔐 Введите логин администратора:", reply_markup=kb_main(is_admin=False))
    await state.set_state(AdminAuth.waiting_login)


@router.message(AdminAuth.waiting_login)
async def admin_login_get_login(m: Message, state: FSMContext):
    await state.update_data(admin_login=(m.text or "").strip())
    await m.answer("Введите пароль администратора:")
    await state.set_state(AdminAuth.waiting_password)


@router.message(AdminAuth.waiting_password)
async def admin_login_get_pass(m: Message, state: FSMContext):
    data = await state.get_data()
    login = data.get("admin_login", "")
    password = (m.text or "").strip()

    if login == settings.ADMIN_LOGIN and password == settings.ADMIN_PASSWORD:
        async with async_session() as session:
            agent = await get_or_create_agent(session, m.from_user.id)
            agent.admin_logged_in = True
            await session.commit()
        await state.clear()
        await m.answer("✅ Админ-вход выполнен.", reply_markup=kb_admin_menu())
    else:
        await state.clear()
        await m.answer("❌ Неверные логин или пароль.", reply_markup=kb_main(is_admin=False))


@router.message(F.text == BTN_ADMIN_LOGOUT)
async def admin_logout(m: Message, state: FSMContext):
    async with async_session() as session:
        agent = await get_or_create_agent(session, m.from_user.id)
        agent.admin_logged_in = False
        await session.commit()
    await state.clear()
    await m.answer("Вы вышли из админ-режима.", reply_markup=kb_main(is_admin=False))


@router.message(F.text == BTN_ADMIN)
async def admin_menu_cmd(m: Message):
    if not await _is_admin_logged(m.from_user.id):
        await m.answer("Доступ запрещён.")
        return
    await m.answer("🛠 Админ-меню", reply_markup=kb_admin_menu())


@router.message(F.text == BTN_ADMIN_HELP)
async def admin_help(m: Message):
    if not await _is_admin_logged(m.from_user.id):
        await m.answer("Доступ запрещён.")
        return
    await m.answer(
        "Экспорт: XLSX и CSV (с выбором периода). "
        "В XLSX: листы data, summary, pivot_multi, pivot_flat. "
        "Также доступна текстовая и XLSX-сводка по всем агентам."
    )


# ===== EXPORT XLSX / CSV =====
@router.message(F.text == BTN_ADMIN_EXPORT_XLSX)
async def admin_export_xlsx_menu(m: Message):
    if not await _is_admin_logged(m.from_user.id):
        await m.answer("Доступ запрещён.")
        return
    await m.answer("📦 Экспорт XLSX — выберите:", reply_markup=kb_admin_export_xlsx())


@router.message(F.text == BTN_XLSX_ALL)
async def admin_export_xlsx_choose_range(m: Message, state: FSMContext):
    if not await _is_admin_logged(m.from_user.id):
        await m.answer("Доступ запрещён.")
        return
    await state.update_data(fmt="xlsx")
    await state.set_state(AdminExport.waiting_range)
    await m.answer("Выберите период:", reply_markup=kb_export_ranges())


@router.message(F.text == BTN_ADMIN_EXPORT_CSV)
async def admin_export_csv_menu(m: Message):
    if not await _is_admin_logged(m.from_user.id):
        await m.answer("Доступ запрещён.")
        return
    await m.answer("📦 Экспорт CSV — выберите:", reply_markup=kb_admin_export_csv())


@router.message(F.text == BTN_CSV_ALL)
async def admin_export_csv_choose_range(m: Message, state: FSMContext):
    if not await _is_admin_logged(m.from_user.id):
        await m.answer("Доступ запрещён.")
        return
    await state.update_data(fmt="csv")
    await state.set_state(AdminExport.waiting_range)
    await m.answer("Выберите период:", reply_markup=kb_export_ranges())


@router.message(AdminExport.waiting_range, F.text.in_([BTN_EXP_TODAY, BTN_EXP_7, BTN_EXP_30, BTN_EXP_ALL, BTN_BACK]))
async def admin_export_do(m: Message, state: FSMContext):
    if not await _is_admin_logged(m.from_user.id):
        await m.answer("Доступ запрещён.")
        return

    if m.text == BTN_BACK:
        await state.clear()
        await m.answer("🛠 Админ-меню", reply_markup=kb_admin_menu())
        return

    # период
    days = None
    label = "за весь период"
    if m.text == BTN_EXP_TODAY:
        days, label = 1, "за сегодня"
    elif m.text == BTN_EXP_7:
        days, label = 7, "за 7 дней"
    elif m.text == BTN_EXP_30:
        days, label = 30, "за 30 дней"

    fmt = (await state.get_data()).get("fmt", "xlsx")

    try:
        async with async_session() as session:
            rows = await list_contacts_for_period(session, days=days)
        df = rows_to_dataframe(rows)
        total = len(df.index)
        if total == 0:
            await state.clear()
            await m.answer("Записей за выбранный период нет.", reply_markup=kb_admin_menu())
            return

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        base = Path(tempfile.gettempdir()) / f"export_{ts}"

        if fmt == "xlsx":
            xlsx_path = base.with_suffix(".xlsx")
            try:
                write_excel_with_pivot(df, str(xlsx_path))
                await m.answer_document(
                    FSInputFile(str(xlsx_path)),
                    caption=f"XLSX ({label}). Строк: {total}."
                )
            except Exception as e:
                logger.exception("XLSX export failed")
                csv_path = base.with_suffix(".csv")
                df.to_csv(str(csv_path), index=False, encoding="utf-8-sig")
                await m.answer_document(
                    FSInputFile(str(csv_path)),
                    caption="XLSX не собрался. Отправляю CSV. Ошибка: " + html.escape(str(e))
                )
        else:
            csv_path = base.with_suffix(".csv")
            df.to_csv(str(csv_path), index=False, encoding="utf-8-sig")
            await m.answer_document(
                FSInputFile(str(csv_path)),
                caption=f"CSV ({label}) — UTF-8 BOM. Строк: {total}."
            )
    except Exception as e:
        logger.exception("Export handler failed")
        await m.answer("Не удалось сформировать экспорт: " + html.escape(str(e)))
    finally:
        await state.clear()
        await m.answer("🛠 Админ-меню", reply_markup=kb_admin_menu())


# ===== STATS: ALL AGENTS =====
@router.message(F.text == BTN_ADMIN_STATS_ALL)
async def admin_stats_all_start(m: Message, state: FSMContext):
    if not await _is_admin_logged(m.from_user.id):
        await m.answer("Доступ запрещён.")
        return
    await m.answer("За какой период показать сводку по всем агентам?", reply_markup=kb_export_ranges())
    await state.set_state(AdminStats.waiting_range)


@router.message(AdminStats.waiting_range, F.text.in_([BTN_EXP_TODAY, BTN_EXP_7, BTN_EXP_30, BTN_EXP_ALL, BTN_BACK]))
async def admin_stats_all_run(m: Message, state: FSMContext):
    if not await _is_admin_logged(m.from_user.id):
        await m.answer("Доступ запрещён.")
        return

    if m.text == BTN_BACK:
        await state.clear()
        await m.answer("🛠 Админ-меню", reply_markup=kb_admin_menu())
        return

    days = None
    if m.text == BTN_EXP_TODAY:
        days = 1
    elif m.text == BTN_EXP_7:
        days = 7
    elif m.text == BTN_EXP_30:
        days = 30

    async with async_session() as local_session:
        stats = await agents_stats_for_period(local_session, days)
        await local_session.commit()

    if not stats or all(s.get("total", 0) == 0 for s in stats):
        await state.clear()
        await m.answer("Данных за выбранный период нет.", reply_markup=kb_admin_menu())
        return

    lines = ["<b>📈 Сводка по всем агентам</b>"]
    for s in stats[:30]:
        uname = s.get("agent_username") or "(без @)"
        name = s.get("agent_name") or ""
        header = f"ID {s.get('agent_id')} {uname} {name}".strip()
        lines.append(
            f"{header}\n"
            f"  Всего: {s.get('total',0)} | Согласие: {s.get('consent',0)} | Отказ: {s.get('refusal',0)} | Никого нет: {s.get('no_one',0)}\n"
            f"  Флаеры — На руки: {s.get('hand',0)} | В ящик: {s.get('mailbox',0)} | Нет: {s.get('none',0)} | Надомка (Да): {s.get('home_yes',0)}"
        )
    await m.answer("\n\n".join(lines))

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    xlsx_path = Path(tempfile.gettempdir()) / f"admin_stats_{ts}.xlsx"
    try:
        write_admin_summary(stats, str(xlsx_path))
        await m.answer_document(FSInputFile(str(xlsx_path)), caption="Полная сводка по всем агентам (XLSX).")
    except Exception as e:
        logger.exception("Admin stats XLSX failed")
        await m.answer("Не удалось сформировать XLSX: " + html.escape(str(e)))

    await state.clear()
    await m.answer("🛠 Админ-меню", reply_markup=kb_admin_menu())


# ====== Доступы (бригадиры) по @username ======

@router.message(F.text == BTN_ADMIN_ACCESS)
async def admin_access_menu(m: Message, state: FSMContext):
    if not await _is_admin_logged(m.from_user.id):
        await m.answer("Доступ запрещён.")
        return
    await state.clear()
    await m.answer("🔑 Доступы (бригадиры):", reply_markup=kb_admin_access_menu())


# — назначить бригадира —
@router.message(F.text == BTN_ACCESS_ADD_BRIG)
async def admin_access_add_brigadier_start(m: Message, state: FSMContext):
    if not await _is_admin_logged(m.from_user.id):
        await m.answer("Доступ запрещён.")
        return
    await state.set_state(AdminAccess.waiting_brig_username)
    await m.answer("Введите @username пользователя, которого назначаем бригадиром (например: @username).")

@router.message(AdminAccess.waiting_brig_username)
async def admin_access_add_brigadier_save(m: Message, state: FSMContext):
    if not await _is_admin_logged(m.from_user.id):
        await state.clear()
        await m.answer("Доступ запрещён.")
        return

    raw = (m.text or "").strip()
    if raw.startswith("@"):
        raw = raw[1:]
    if not raw:
        await m.answer("Укажите корректный username (например, @username).")
        return

    async with async_session() as session:
        await ensure_brig_tables(session)
        tg_id = await resolve_username_to_tg(session, raw)
        if not tg_id:
            await m.answer("Пользователь не найден в базе. Он должен хотя бы раз написать боту.")
            return
        await add_brigadier(session, tg_id)
        await session.commit()

    await state.clear()
    await m.answer(f"✅ @{raw} назначен бригадиром.", reply_markup=kb_admin_access_menu())


# — привязать участника к бригадиру —
@router.message(F.text == BTN_ACCESS_ATTACH_MEMBER)
async def admin_access_attach_start(m: Message, state: FSMContext):
    if not await _is_admin_logged(m.from_user.id):
        await m.answer("Доступ запрещён.")
        return
    await state.set_state(AdminAccess.waiting_attach_brig_username)
    await m.answer("Введите @username бригадира, к которому нужно привязать участника.")

@router.message(AdminAccess.waiting_attach_brig_username)
async def admin_access_attach_get_member(m: Message, state: FSMContext):
    raw = (m.text or "").strip()
    if raw.startswith("@"):
        raw = raw[1:]
    if not raw:
        await m.answer("Введите корректный @username бригадира.")
        return
    await state.update_data(brig_username=raw)
    await state.set_state(AdminAccess.waiting_attach_member_username)
    await m.answer("Теперь введите @username участника, которого нужно привязать.")

@router.message(AdminAccess.waiting_attach_member_username)
async def admin_access_attach_save(m: Message, state: FSMContext):
    if not await _is_admin_logged(m.from_user.id):
        await state.clear()
        await m.answer("Доступ запрещён.")
        return

    raw = (m.text or "").strip()
    if raw.startswith("@"):
        raw = raw[1:]
    if not raw:
        await m.answer("Введите корректный @username участника.")
        return

    data = await state.get_data()
    brig_username = data.get("brig_username")

    async with async_session() as session:
        await ensure_brig_tables(session)
        brig_tg = await resolve_username_to_tg(session, brig_username or "")
        member_tg = await resolve_username_to_tg(session, raw)
        if not brig_tg:
            await m.answer(f"Бригадир @{brig_username} не найден в базе.")
            return
        if not member_tg:
            await m.answer(f"Участник @{raw} не найден в базе.")
            return

        await set_brig_member(session, brig_tg, member_tg)
        await session.commit()

    await state.clear()
    await m.answer(f"✅ Участник @{raw} привязан к бригадиру @{brig_username}.", reply_markup=kb_admin_access_menu())


# — список бригадиров —
@router.message(F.text == BTN_ACCESS_LIST)
async def admin_access_list_brigadiers(m: Message):
    if not await _is_admin_logged(m.from_user.id):
        await m.answer("Доступ запрещён.")
        return

    async with async_session() as session:
        await ensure_brig_tables(session)
        items = await list_brigadiers(session)

        # Подтянем известные username/имена из таблицы Agent
        # создадим карты tg_id -> (@username, name)
        res = await session.execute(select(Agent))
        agents = res.scalars().all()
        uname_by_tg = {a.tg_user_id: (f"@{a.username}" if a.username else "", a.name or "") for a in agents}

    if not items:
        await m.answer("Бригадиров ещё нет.", reply_markup=kb_admin_access_menu())
        return

    lines = ["<b>📋 Бригадиры</b>"]
    for it in items:
        b_id = it["brig_tg_id"]
        b_un, b_name = uname_by_tg.get(b_id, ("", ""))
        header = f"{b_id} {b_un} {b_name}".strip()
        lines.append(header)
        for mid in it.get("members", []):
            m_un, m_name = uname_by_tg.get(mid, ("", ""))
            lines.append(f"  └─ {mid} {m_un} {m_name}".rstrip())

    await m.answer("\n".join(lines), reply_markup=kb_admin_access_menu())

@router.message(AdminDemoteBrig.waiting_username_or_id)
async def admin_access_demote_brig_finish(m: Message, state: FSMContext):
    raw = (m.text or "").strip()

    if raw == BTN_BACK or raw.lower() in ("отмена", "cancel"):
        await state.clear()
        await m.answer("Отменено.", reply_markup=kb_admin_access_menu())
        return

    tg_id: int | None = None

    if raw.startswith("@"):
        uname = raw.lstrip("@")
        async with async_session() as session:
            agent = await get_agent_by_username(session, uname)
            if not agent:
                await m.answer("Не нашёл такого @username. Убедитесь, что человек писал боту.")
                return
            tg_id = int(agent.tg_user_id)
    else:
        if not raw.isdigit():
            await m.answer("Нужен @username или числовой Telegram ID.")
            return
        tg_id = int(raw)

    async with async_session() as session:
        await demote_brigadier(session, tg_id)
        await session.commit()

    await state.clear()
    await m.answer(f"✅ Пользователь {'@'+uname if raw.startswith('@') else tg_id} разжалован из бригадиров.",
                   reply_markup=kb_admin_access_menu())

