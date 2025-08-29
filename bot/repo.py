from __future__ import annotations

from typing import Iterable, Optional, List, Dict
from hashlib import sha256
from datetime import datetime, timedelta
import re
from sqlalchemy import func

from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from .models import Agent, Visit, Contact, RepeatTouch, TalkStatus, FlyerMethod

# ==========================
# Общие хелперы
# ==========================

def phone_hash(phone_e164: str) -> str:
    """Хеш телефона для приватности (e164 → sha256)."""
    return sha256(phone_e164.encode()).hexdigest()

# ==========================
# Агенты
# ==========================

async def get_or_create_agent(
    session: AsyncSession,
    tg_user_id: int,
    *,
    name: Optional[str] = None,
    username: Optional[str] = None,
) -> Agent:
    """Вернёт агента; создаст при первом входе. Обновляет name/username при изменениях."""
    res = await session.execute(select(Agent).where(Agent.tg_user_id == tg_user_id))
    agent = res.scalars().first()
    if agent:
        changed = False
        if name and agent.name != name:
            agent.name = name
            changed = True
        if username and agent.username != username:
            agent.username = username
            changed = True
        if changed:
            await session.flush()
        return agent

    # create
    agent = Agent(tg_user_id=tg_user_id, name=name, username=username)
    session.add(agent)
    try:
        await session.flush()
        return agent
    except IntegrityError:
        # гонка: кто-то создал параллельно
        await session.rollback()
        res = await session.execute(select(Agent).where(Agent.tg_user_id == tg_user_id))
        agent = res.scalars().first()
        if agent:
            changed = False
            if name and agent.name != name:
                agent.name = name
                changed = True
            if username and agent.username != username:
                agent.username = username
                changed = True
            if changed:
                await session.flush()
            return agent
        session.add(Agent(tg_user_id=tg_user_id, name=name, username=username))
        await session.flush()
        res = await session.execute(select(Agent).where(Agent.tg_user_id == tg_user_id))
        return res.scalars().first()

# ==========================
# Визиты
# ==========================

async def create_visit(session: AsyncSession, agent_id: int, address: str | None = None) -> Visit:
    visit = Visit(agent_id=agent_id, address=address)
    session.add(visit)
    await session.flush()
    return visit

async def close_visit(session: AsyncSession, visit_id: int) -> None:
    res = await session.execute(select(Visit).where(Visit.id == visit_id))
    v = res.scalars().first()
    if v and not v.closed_at:
        v.closed_at = datetime.utcnow()
        await session.flush()

# ==========================
# Контакты
# ==========================

async def create_contact(
    session: AsyncSession,
    *,
    visit_id: int,
    agent_id: int,
    full_name: str,
    phone_e164: str,
) -> Contact:
    c = Contact(
        visit_id=visit_id,
        agent_id=agent_id,
        full_name=full_name,
        phone_e164=phone_e164,
        phone_hash=phone_hash(phone_e164),
    )
    session.add(c)
    await session.flush()
    return c

async def update_contact_fields(session: AsyncSession, contact_id: int, **fields) -> Contact | None:
    await session.execute(update(Contact).where(Contact.id == contact_id).values(**fields))
    res = await session.execute(select(Contact).where(Contact.id == contact_id))
    return res.scalars().first()

async def close_contact(session: AsyncSession, contact_id: int) -> None:
    res = await session.execute(select(Contact).where(Contact.id == contact_id))
    c = res.scalars().first()
    if c and not c.closed_at:
        c.closed_at = datetime.utcnow()
        await session.flush()

# ==========================
# Выгрузки / выборки
# ==========================

async def list_contacts_for_period(session: AsyncSession, *, days: int | None):
    """
    Список (Contact, Agent) за период (days) или за весь период (None).
    Сортировка — от новых к старым.
    """
    q = (
        select(Contact, Agent)
        .join(Agent, Contact.agent_id == Agent.id, isouter=True)
    )
    if days is not None:
        since = datetime.utcnow() - timedelta(days=days)
        q = q.where(Contact.created_at >= since)
    q = q.order_by(Contact.created_at.desc())
    res = await session.execute(q)
    return res.all()

# ==========================
# Номера флаеров
# ==========================

async def flyer_exists(session: AsyncSession, num: int | str) -> bool:
    """
    Проверка занятости номера флаера.
    Сравнивает по числовому значению; мусорные/нечисловые значения в БД игнорируются.
    """
    try:
        target = int(str(num).strip())
    except (TypeError, ValueError):
        return False

    res = await session.execute(
        select(Contact.flyer_number).where(Contact.flyer_number.is_not(None))
    )
    for (val,) in res:
        s = str(val).strip()
        if not s.isdigit():
            continue
        if int(s) == target:
            return True
    return False

async def get_next_flyer_number(session: AsyncSession) -> int:
    """
    «Следующий» номер (максимум+1), игнорируя нечисловые/вне диапазона значения.
    """
    res = await session.execute(
        select(Contact.flyer_number).where(Contact.flyer_number.is_not(None))
    )
    max_num = 0
    for (val,) in res:
        s = str(val).strip() if val is not None else ""
        if not s.isdigit():
            continue
        n = int(s)
        if 1 <= n <= 30_000_000 and n > max_num:
            max_num = n
    return max_num + 1 if max_num > 0 else 1

# ==========================
# Статистика
# ==========================

async def agent_stats_last24h(session: AsyncSession, agent_id: int) -> dict:
    """Личная статистика агента за 24 часа."""
    since = datetime.utcnow() - timedelta(hours=24)
    q = select(Contact).where(Contact.agent_id == agent_id, Contact.created_at >= since)
    res = await session.execute(q)
    rows = res.scalars().all()

    total = len(rows)
    status = {"CONSENT": 0, "REFUSAL": 0, "NO_ONE": 0}
    flyer = {"HAND": 0, "MAILBOX": 0, "NONE": 0}
    home_yes = 0

    for c in rows:
        if c.talk_status:
            status[c.talk_status.value] = status.get(c.talk_status.value, 0) + 1
        if c.flyer_method:
            flyer[c.flyer_method.value] = flyer.get(c.flyer_method.value, 0) + 1
        if c.home_voting:
            home_yes += 1

    return {"total": total, "status": status, "flyer": flyer, "home_yes": home_yes}

async def agents_stats_for_period(session: AsyncSession, days: int | None):
    """
    Сводка по всем агентам за период (или за всё время).
    Возвращает список словарей, отсортированный по убыванию total.
    """
    # карта агентов
    res = await session.execute(select(Agent))
    agents = res.scalars().all()
    stats = {
        a.id: {
            "agent_id": a.id,
            "agent_tg": a.tg_user_id,
            "agent_username": (f"@{a.username}" if getattr(a, "username", None) else ""),
            "agent_name": a.name or "",
            "total": 0,
            "consent": 0,
            "refusal": 0,
            "no_one": 0,
            "hand": 0,
            "mailbox": 0,
            "none": 0,
            "home_yes": 0,
        }
        for a in agents
    }

    # контакты
    q = select(Contact)
    if days is not None:
        since = datetime.utcnow() - timedelta(days=days)
        q = q.where(Contact.created_at >= since)
    res = await session.execute(q)
    rows = res.scalars().all()

    for c in rows:
        aid = c.agent_id
        if aid not in stats:
            stats[aid] = {
                "agent_id": aid,
                "agent_tg": None,
                "agent_username": "",
                "agent_name": "",
                "total": 0,
                "consent": 0,
                "refusal": 0,
                "no_one": 0,
                "hand": 0,
                "mailbox": 0,
                "none": 0,
                "home_yes": 0,
            }
        s = stats[aid]
        s["total"] += 1

        if c.talk_status:
            v = c.talk_status.value
            if v == "CONSENT":
                s["consent"] += 1
            elif v == "REFUSAL":
                s["refusal"] += 1
            elif v == "NO_ONE":
                s["no_one"] += 1

        if c.flyer_method:
            v = c.flyer_method.value
            if v == "HAND":
                s["hand"] += 1
            elif v == "MAILBOX":
                s["mailbox"] += 1
            elif v == "NONE":
                s["none"] += 1

        if c.home_voting:
            s["home_yes"] += 1

    return sorted(stats.values(), key=lambda x: x["total"], reverse=True)

# ==========================
# БРИГАДИРЫ (доступы/привязки)
# Таблицы (SQLite/Postgres совместимо):
#  - brigadiers(brig_tg_id PK)
#  - brig_sessions(brig_tg_id PK, logged_in INT)
#  - brig_members(brig_tg_id, member_tg_id, PK (brig_tg_id, member_tg_id))
# ==========================

async def _table_info(session: AsyncSession, table: str) -> list[dict]:
    res = await session.execute(text(f"PRAGMA table_info({table})"))
    rows = res.all()
    # rows: (cid, name, type, notnull, dflt_value, pk)
    return [{"cid": r[0], "name": r[1], "type": r[2], "notnull": r[3], "dflt": r[4], "pk": r[5]} for r in rows]

async def ensure_brig_tables(session: AsyncSession) -> None:
    # ---- brigadiers: ensure schema ----
    info = await _table_info(session, "brigadiers")
    need_migrate = False
    if not info:
        # table doesn't exist — create
        await session.execute(text("""
            CREATE TABLE brigadiers (
                brig_tg_id BIGINT PRIMARY KEY
            )
        """))
    else:
        cols = {c["name"] for c in info}
        if "brig_tg_id" not in cols or len(cols) != 1:
            need_migrate = True

    if need_migrate:
        # Try to migrate data from any plausible column (brig_tg_id/brig_id/tg_id/id)
        src_cols = [c["name"] for c in info]
        candidate = None
        for name in ("brig_tg_id", "brig_id", "tg_id", "id"):
            if name in src_cols:
                candidate = name
                break

        await session.execute(text("ALTER TABLE brigadiers RENAME TO brigadiers_old"))
        await session.execute(text("CREATE TABLE brigadiers (brig_tg_id BIGINT PRIMARY KEY)"))
        if candidate:
            await session.execute(text(f"""
                INSERT OR IGNORE INTO brigadiers (brig_tg_id)
                SELECT {candidate} FROM brigadiers_old
                WHERE {candidate} IS NOT NULL
            """))
        await session.execute(text("DROP TABLE brigadiers_old"))

    # ---- brig_sessions ----
    info = await _table_info(session, "brig_sessions")
    migrate = False
    if not info:
        await session.execute(text("""
            CREATE TABLE brig_sessions (
                brig_tg_id BIGINT PRIMARY KEY,
                logged_in INTEGER NOT NULL DEFAULT 0
            )
        """))
    else:
        cols = {c["name"] for c in info}
        if not {"brig_tg_id", "logged_in"}.issubset(cols) or len(cols) != 2:
            migrate = True
    if migrate:
        await session.execute(text("ALTER TABLE brig_sessions RENAME TO brig_sessions_old"))
        await session.execute(text("""
            CREATE TABLE brig_sessions (
                brig_tg_id BIGINT PRIMARY KEY,
                logged_in INTEGER NOT NULL DEFAULT 0
            )
        """))
        # попытка миграции
        old_cols = {c["name"] for c in info}
        if "brig_tg_id" in old_cols and "logged_in" in old_cols:
            await session.execute(text("""
                INSERT OR IGNORE INTO brig_sessions (brig_tg_id, logged_in)
                SELECT brig_tg_id, logged_in FROM brig_sessions_old
            """))
        await session.execute(text("DROP TABLE brig_sessions_old"))

    # ---- brig_members ----
    info = await _table_info(session, "brig_members")
    migrate = False
    if not info:
        await session.execute(text("""
            CREATE TABLE brig_members (
                brig_tg_id   BIGINT NOT NULL,
                member_tg_id BIGINT NOT NULL,
                PRIMARY KEY (brig_tg_id, member_tg_id)
            )
        """))
    else:
        cols = {c["name"] for c in info}
        if not {"brig_tg_id", "member_tg_id"}.issubset(cols) or len(cols) != 2:
            migrate = True
    if migrate:
        await session.execute(text("ALTER TABLE brig_members RENAME TO brig_members_old"))
        await session.execute(text("""
            CREATE TABLE brig_members (
                brig_tg_id   BIGINT NOT NULL,
                member_tg_id BIGINT NOT NULL,
                PRIMARY KEY (brig_tg_id, member_tg_id)
            )
        """))
        old_cols = {c["name"] for c in info}
        if {"brig_tg_id", "member_tg_id"}.issubset(old_cols):
            await session.execute(text("""
                INSERT OR IGNORE INTO brig_members (brig_tg_id, member_tg_id)
                SELECT brig_tg_id, member_tg_id FROM brig_members_old
            """))
        await session.execute(text("DROP TABLE brig_members_old"))

    # ---- blocked members ----
    try:
        info = await _table_info(session, "blocked_members")
    except Exception:
        info = []
    if not info:
        await session.execute(text(
            """
            CREATE TABLE blocked_members (
                member_tg_id BIGINT PRIMARY KEY,
                blocked_by   BIGINT
            )
            """
        ))

# ---- назначение/проверка бригадиров

async def add_brigadier(session: AsyncSession, brig_tg_id: int) -> None:
    await ensure_brig_tables(session)
    await session.execute(
        text("INSERT OR IGNORE INTO brigadiers (brig_tg_id) VALUES (:b)"),
        {"b": brig_tg_id},
    )

async def is_brigadier_allowed(session: AsyncSession, tg_user_id: int) -> bool:
    await ensure_brig_tables(session)
    res = await session.execute(
        text("SELECT 1 FROM brigadiers WHERE brig_tg_id=:b LIMIT 1"),
        {"b": tg_user_id},
    )
    return res.first() is not None

# ---- вход/выход бригадира

async def set_brig_login(session: AsyncSession, brig_tg_id: int, logged: bool) -> None:
    await ensure_brig_tables(session)
    await session.execute(
        text("""
            INSERT INTO brig_sessions (brig_tg_id, logged_in)
            VALUES (:b, :f)
            ON CONFLICT(brig_tg_id) DO UPDATE SET logged_in=:f
        """),
        {"b": brig_tg_id, "f": 1 if logged else 0},
    )

async def is_brig_logged_in(session: AsyncSession, brig_tg_id: int) -> bool:
    await ensure_brig_tables(session)
    res = await session.execute(
        text("SELECT logged_in FROM brig_sessions WHERE brig_tg_id=:b"),
        {"b": brig_tg_id},
    )
    row = res.first()
    return bool(row and row[0])

# ---- привязки участников

async def set_brig_member(session: AsyncSession, brig_tg_id: int, member_tg_id: int) -> None:
    """Привязать участника (по его Telegram ID) к бригадиру (по его Telegram ID)."""
    await ensure_brig_tables(session)
    # убедимся, что бригадир существует
    await add_brigadier(session, brig_tg_id)
    # idempotent insert
    await session.execute(
        text("""
            INSERT OR IGNORE INTO brig_members (brig_tg_id, member_tg_id)
            VALUES (:b, :m)
        """),
        {"b": brig_tg_id, "m": member_tg_id},
    )

async def remove_brig_member(session: AsyncSession, brig_tg_id: int, member_tg_id: int) -> None:
    await ensure_brig_tables(session)
    await session.execute(
        text("DELETE FROM brig_members WHERE brig_tg_id=:b AND member_tg_id=:m"),
        {"b": brig_tg_id, "m": member_tg_id},
    )

async def list_brigadiers(session: AsyncSession) -> List[Dict]:
    """[{brig_tg_id: int, username: str|None, name: str|None, members: [tg_id, ...]}, ...]"""
    await ensure_brig_tables(session)

    rows_b = (await session.execute(
        text("SELECT brig_tg_id FROM brigadiers ORDER BY brig_tg_id")
    )).all()
    rows_m = (await session.execute(
        text("SELECT brig_tg_id, member_tg_id FROM brig_members ORDER BY brig_tg_id, member_tg_id")
    )).all()

    members_by_brig: Dict[int, list] = {}
    for b_id, m_id in rows_m:
        members_by_brig.setdefault(int(b_id), []).append(int(m_id))

    # подтянем username/name из таблицы agents (если такой агент уже есть)
    result: List[Dict] = []
    for (b_id,) in rows_b:
        b_id_int = int(b_id)
        agent_row = await session.execute(select(Agent).where(Agent.tg_user_id == b_id_int))
        agent = agent_row.scalars().first()
        result.append({
            "brig_tg_id": b_id_int,
            "username": agent.username if agent and agent.username else None,
            "name": agent.name if agent and agent.name else None,
            "members": members_by_brig.get(b_id_int, []),
        })
    return result

# ---- вспомогательное: список Agent.id по членам бригады (их TG ID)

async def list_brigadier_member_agent_ids(session: AsyncSession, brig_tg_id: int) -> List[int]:
    """
    Для бригадира (tg id) вернуть список внутренних Agent.id
    по привязанным member_tg_id (если такие агенты существуют).
    """
    await ensure_brig_tables(session)
    rows = (await session.execute(
        text("SELECT member_tg_id FROM brig_members WHERE brig_tg_id=:b"),
        {"b": brig_tg_id},
    )).all()
    member_tg_ids = [int(r[0]) for r in rows]

    if not member_tg_ids:
        return []

    res = await session.execute(select(Agent.id).where(Agent.tg_user_id.in_(member_tg_ids)))
    return [int(x[0]) for x in res.all()]

# --- Алиасы для совместимости со старыми импортами ---

async def link_agent_to_brigadier(session: AsyncSession, brig_tg_id: int, member_agent_id: int) -> None:
    """
    Старый интерфейс: принимает ИД агента (Agent.id).
    Находим его tg_user_id и делаем set_brig_member(...).
    """
    agent_row = await session.execute(select(Agent).where(Agent.id == member_agent_id))
    agent = agent_row.scalars().first()
    if not agent:
        raise ValueError(f"Agent with id={member_agent_id} not found")
    await set_brig_member(session, brig_tg_id=brig_tg_id, member_tg_id=int(agent.tg_user_id))

async def unlink_agent_from_brigadier(session: AsyncSession, brig_tg_id: int, member_agent_id: int) -> None:
    """Удалить привязку по старому интерфейсу (по Agent.id)."""
    agent_row = await session.execute(select(Agent).where(Agent.id == member_agent_id))
    agent = agent_row.scalars().first()
    if not agent:
        return
    await remove_brig_member(session, brig_tg_id=brig_tg_id, member_tg_id=int(agent.tg_user_id))

async def list_brigadier_agent_ids(session: AsyncSession, brig_tg_id: int) -> list[int]:
    """Совместимый алиас: вернуть список Agent.id по членам бригады."""
    return await list_brigadier_member_agent_ids(session, brig_tg_id)

def _clean_username(u: str) -> str:
    # @User_Name → "user_name"
    return re.sub(r'[^a-z0-9_]', '', (u or '').strip().lstrip('@').lower())

async def get_agent_by_username(session: AsyncSession, username: str) -> Agent | None:
    uname = _clean_username(username)
    if not uname:
        return None
    res = await session.execute(
        select(Agent).where(func.lower(Agent.username) == uname)
    )
    return res.scalars().first()

async def add_brigadier_by_username(session: AsyncSession, username: str) -> int:
    """
    Назначить бригадира по @username. Возвращает tg_user_id бригадира.
    Если пользователь еще не писал боту — вернётся ошибка.
    """
    agent = await get_agent_by_username(session, username)
    if not agent:
        raise ValueError("Пользователь с таким @username не найден в базе. "
                         "Он должен один раз написать боту, чтобы появиться.")
    await add_brigadier(session, int(agent.tg_user_id))
    return int(agent.tg_user_id)

async def set_brig_member_by_usernames(
    session: AsyncSession, brig_username: str, member_username: str
) -> tuple[int, int]:
    """
    Привязать участника к бригадиру по @username.
    Возвращает (brig_tg_id, member_tg_id).
    """
    brig = await get_agent_by_username(session, brig_username)
    if not brig:
        raise ValueError("Бригадир с таким @username не найден в базе.")
    mem = await get_agent_by_username(session, member_username)
    if not mem:
        raise ValueError("Участник с таким @username не найден в базе.")

    await set_brig_member(session, int(brig.tg_user_id), int(mem.tg_user_id))
    return int(brig.tg_user_id), int(mem.tg_user_id)

# ---- NEW: совместимость с admin.py импортом ----

async def resolve_username_to_tg(session: AsyncSession, username: str) -> int | None:
    """
    Вернуть Telegram ID по @username из таблицы Agent.
    Пользователь появится в базе после первого сообщения боту.
    """
    agent = await get_agent_by_username(session, username)
    return int(agent.tg_user_id) if agent else None


# ==========================
# Блокировки участников
# ==========================

async def block_member(session: AsyncSession, *, member_tg_id: int, blocked_by: int) -> None:
    await ensure_brig_tables(session)
    await session.execute(
        text("INSERT OR REPLACE INTO blocked_members (member_tg_id, blocked_by) VALUES (:m, :b)"),
        {"m": member_tg_id, "b": blocked_by},
    )

async def unblock_member(session: AsyncSession, *, member_tg_id: int) -> None:
    await ensure_brig_tables(session)
    await session.execute(text("DELETE FROM blocked_members WHERE member_tg_id=:m"), {"m": member_tg_id})

async def is_member_blocked(session: AsyncSession, tg_user_id: int) -> bool:
    await ensure_brig_tables(session)
    res = await session.execute(text("SELECT 1 FROM blocked_members WHERE member_tg_id=:m LIMIT 1"), {"m": tg_user_id})
    return res.first() is not None

async def block_member_by_username(session: AsyncSession, member_username: str, *, blocked_by: int) -> int:
    agent = await get_agent_by_username(session, member_username)
    if not agent:
        raise ValueError("Участник с таким @username не найден в базе. Он должен один раз написать боту.")
    await block_member(session, member_tg_id=int(agent.tg_user_id), blocked_by=blocked_by)
    return int(agent.tg_user_id)

async def unblock_member_by_username(session: AsyncSession, member_username: str) -> int:
    agent = await get_agent_by_username(session, member_username)
    if not agent:
        raise ValueError("Участник с таким @username не найден в базе.")
    await unblock_member(session, member_tg_id=int(agent.tg_user_id))
    return int(agent.tg_user_id)

async def demote_brigadier(session, tg_user_id: int) -> None:
    """Снять права бригадира: удалить из brigadiers, разлогинить, отвязать подопечных."""
    # снять из белого списка бригадиров
    await session.execute(text("DELETE FROM brigadiers WHERE brig_tg_id = :tg"), {"tg": tg_user_id})

    # разлогинить (если используешь флаг логина в agents или где-то ещё)
    try:
        from .repo import set_brig_login  # если эта функция в этом же файле — просто вызови напрямую
    except Exception:
        pass
    # если функция в этом же файле, просто:
    await set_brig_login(session, tg_user_id, False)

    # отвязать всех его участников (если есть таблица связки)
    try:
        await session.execute(text("DELETE FROM brig_members WHERE brig_tg_id = :tg"), {"tg": tg_user_id})
    except Exception:
        # если таблицы нет — тихо игнорируем
        pass
