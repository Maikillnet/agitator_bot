from __future__ import annotations
import io
from datetime import datetime

import pandas as pd
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, BufferedInputFile

from ..db import async_session
from ..repo import get_or_create_agent, agent_stats_last24h, agents_stats_for_period
from ..keyboards import (
    BTN_MY_STATS,
    BTN_AGENT_EXPORT_XLSX,
    BTN_EXP_TODAY, BTN_EXP_7, BTN_EXP_30, BTN_EXP_ALL, BTN_BACK,
    kb_export_ranges, kb_main,
)

router = Router(name="stats")


# ===== Твоя «Сводка за смену» как была =====
@router.message(F.text == BTN_MY_STATS)
async def my_stats(m: Message):
    async with async_session() as session:
        display_name = " ".join(filter(None, [m.from_user.first_name, m.from_user.last_name])).strip() or None
        username = m.from_user.username or None
        agent = await get_or_create_agent(session, m.from_user.id, name=display_name, username=username)
        stats = await agent_stats_last24h(session, agent.id)
        await session.commit()

    uname = f"@{agent.username}" if agent.username else "(без @)"
    who = agent.name or uname
    text = (
        f"📊 Сводка за 24 часа для {who} {uname}\n"
        f"Всего карточек: <b>{stats['total']}</b>\n\n"
        f"Статусы:\n"
        f"— Согласие: {stats['status'].get('CONSENT',0)}\n"
        f"— Отказ: {stats['status'].get('REFUSAL',0)}\n"
        f"— Никого нет: {stats['status'].get('NO_ONE',0)}\n\n"
        f"Флаеры:\n"
        f"— На руки: {stats['flyer'].get('HAND',0)}\n"
        f"— В ящик: {stats['flyer'].get('MAILBOX',0)}\n"
        f"— Нет: {stats['flyer'].get('NONE',0)}\n\n"
        f"Голосование на дому (Да): {stats['home_yes']}"
    )
    await m.answer(text)


# ===== Личный экспорт XLSX =====
class AgentExport(StatesGroup):
    waiting_range = State()


@router.message(F.text == BTN_AGENT_EXPORT_XLSX)
async def agent_export_start(m: Message, state: FSMContext):
    await state.set_state(AgentExport.waiting_range)
    await m.answer("За какой период сделать выгрузку XLSX только по моим карточкам?", reply_markup=kb_export_ranges())


@router.message(
    AgentExport.waiting_range,
    F.text.in_([BTN_EXP_TODAY, BTN_EXP_7, BTN_EXP_30, BTN_EXP_ALL, BTN_BACK]),
)
async def agent_export_run(m: Message, state: FSMContext):
    # Назад — в главное меню
    if m.text == BTN_BACK:
        await state.clear()
        async with async_session() as session:
            agent = await get_or_create_agent(session, m.from_user.id)
            await session.commit()
        await m.answer(
            "Главное меню.",
            reply_markup=kb_main(
                is_admin=bool(getattr(agent, "admin_logged_in", False)),
                is_brig=bool(getattr(agent, "brig_logged_in", False)),
            ),
        )
        return

    # Период
    days, title = None, "за весь период"
    if m.text == BTN_EXP_TODAY:
        days, title = 1, "за 1 день"
    elif m.text == BTN_EXP_7:
        days, title = 7, "за 7 дней"
    elif m.text == BTN_EXP_30:
        days, title = 30, "за 30 дней"

    # Агент + агрегированная статистика за период
    async with async_session() as session:
        display_name = " ".join(filter(None, [m.from_user.first_name, m.from_user.last_name])) or None
        username = m.from_user.username or None
        agent = await get_or_create_agent(session, m.from_user.id, name=display_name, username=username)
        all_stats = await agents_stats_for_period(session, days)
        await session.commit()

    my = next((s for s in all_stats if s.get("agent_id") == agent.id), None)
    if not my:
        await state.clear()
        await m.answer(
            "За выбранный период по вам нет данных.",
            reply_markup=kb_main(
                is_admin=bool(getattr(agent, "admin_logged_in", False)),
                is_brig=bool(getattr(agent, "brig_logged_in", False)),
            ),
        )
        return

    # Текстовая сводка (для быстрого просмотра)
    uname = f"@{agent.username}" if agent.username else "(без @)"
    who = agent.name or uname
    text = (
        f"📊 Моя сводка ({title})\n"
        f"Всего карточек: <b>{my.get('total',0)}</b>\n\n"
        f"Статусы:\n"
        f"— Согласие: {my.get('consent',0)}\n"
        f"— Отказ: {my.get('refusal',0)}\n"
        f"— Никого нет: {my.get('no_one',0)}\n\n"
        f"Флаеры:\n"
        f"— На руки: {my.get('hand',0)}\n"
        f"— В ящик: {my.get('mailbox',0)}\n"
        f"— Нет: {my.get('none',0)}\n\n"
        f"Голосование на дому (Да): {my.get('home_yes',0)}"
    )
    await m.answer(text)

    # ===== XLSX в памяти (1 строка-агрегат) с русской шапкой =====
    rows = [{
        "username": agent.username or "",
        "name":     agent.name or "",
        "period":   title,
        "total":    my.get("total", 0),
        "consent":  my.get("consent", 0),
        "refusal":  my.get("refusal", 0),
        "no_one":   my.get("no_one", 0),
        "hand":     my.get("hand", 0),
        "mailbox":  my.get("mailbox", 0),
        "none":     my.get("none", 0),
        "home_yes": my.get("home_yes", 0),
    }]

    order = ["username","name","period","total","consent","refusal","no_one","hand","mailbox","none","home_yes"]
    header_map = {
        "username": "Логин (@)",
        "name": "Имя",
        "period": "Период",
        "total": "Всего",
        "consent": "Согласие",
        "refusal": "Отказ",
        "no_one": "Никого нет",
        "hand": "Флаер — на руки",
        "mailbox": "Флаер — в ящик",
        "none": "Флаер — не выдавали",
        "home_yes": "Голосование на дому (Да)",
    }

    df = pd.DataFrame(rows)[order].rename(columns=header_map)

    bio = io.BytesIO()
    try:
        with pd.ExcelWriter(bio, engine="xlsxwriter") as w:
            sheet = "Моя сводка"
            df.to_excel(w, index=False, sheet_name=sheet)
            ws = w.sheets[sheet]

            # Читаемые ширины колонок
            widths = [16, 24, 14, 10, 10, 10, 12, 16, 16, 20, 22]
            for i, width in enumerate(widths):
                ws.set_column(i, i, width)

            # Жирная шапка
            header_fmt = w.book.add_format({"bold": True})
            ws.set_row(0, None, header_fmt)
    except Exception:
        # fallback на openpyxl
        with pd.ExcelWriter(bio, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name="Моя сводка")

    data = bio.getvalue()
    filename = f"my_stats_{(days or 0)}d_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    await m.answer_document(BufferedInputFile(data, filename=filename))
    await state.clear()
