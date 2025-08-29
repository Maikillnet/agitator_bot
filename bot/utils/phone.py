# bot/utils/phone.py
from __future__ import annotations
import re

def normalize_phone(raw: str | None) -> str | None:
    """
    Приводит любой ввод к формату E.164 для РФ: "+7XXXXXXXXXX".
    Допускает ввод с пробелами/скобками/дефисами, ведущей 8, просто 10 цифр и т.п.
    Любые нецифровые символы (включая '?', '+', пробелы) удаляются.
    """
    if not raw:
        return None

    digits = re.sub(r"\D+", "", raw)  # оставляем только цифры

    # варианты ввода: +7XXXXXXXXXX / 8XXXXXXXXXX / 7XXXXXXXXXX / XXXXXXXXXX
    if len(digits) == 11 and digits.startswith(("7", "8")):
        # берём последние 10 как национальный номер
        digits = "7" + digits[-10:]
    elif len(digits) == 10:
        digits = "7" + digits
    else:
        return None

    # итог только для РФ
    if digits.startswith("7") and len(digits) == 11:
        return f"+{digits}"
    return None


def phone_for_api(e164: str | None) -> str | None:
    """
    Для внешнего API нужен ровно 10-значный номер БЕЗ '+7'.
    На вход подаётся строка E.164 вида '+7XXXXXXXXXX'.
    """
    if not e164 or not e164.startswith("+7"):
        return None
    # '+7' + 10 цифр => возвращаем последние 10
    rest = e164[2:]
    return rest if len(rest) == 10 and rest.isdigit() else None
