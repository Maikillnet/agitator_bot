# bot/utils/webhook.py
from __future__ import annotations
import aiohttp
from .phone import normalize_phone, phone_for_api

STIMUL_API_URL = "https://stimul.app/pub-api/v1/arch/set-lottery-code"
TIMEOUT = 10  # сек

async def send_lottery_code(phone_raw: str, code: str, voting_at_home: bool):
    """
    Шлёт на внешний сервис JSON:
      {
        "phone": "1234567890",          # 10 цифр, без +7
        "code": "12345",                # строка
        "voting_at_home": true/false    # bool
      }
    Возвращает (ok: bool, msg: str).
    """
    # 1) нормализуем к +7XXXXXXXXXX
    e164 = normalize_phone(phone_raw)
    if not e164:
        return False, f"[webhook] fail: phone is empty or invalid after normalization (raw='{phone_raw or ''}')"

    # 2) переводим к 10 цифрам без +7
    phone10 = phone_for_api(e164)
    if not phone10:
        return False, "[webhook] fail: cannot build 10-digit phone for API"

    payload = {
        "phone": phone10,
        "code": str(code).strip(),
        "voting_at_home": bool(voting_at_home),
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as s:
            async with s.post(STIMUL_API_URL, json=payload) as r:
                body = await r.text()
                if 200 <= r.status < 300:
                    return True, "[webhook] ok"
                return False, f"[webhook] fail: HTTP {r.status}: {body}"
    except Exception as e:
        return False, f"[webhook] fail: {e!r}"
