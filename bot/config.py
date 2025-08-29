# bot/config.py
from dataclasses import dataclass
from aiogram.client.default import DefaultBotProperties
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = (ROOT_DIR / "data.db").as_posix()

@dataclass(frozen=True)
class Settings:
    BOT_TOKEN: str
    ADMIN_LOGIN: str
    ADMIN_PASSWORD: str
    DB_URL: str
    DATABASE_URL: str
    DEFAULT_BOT_PROPS: DefaultBotProperties

settings = Settings(
    BOT_TOKEN="8266987716:AAFXcHOrpC68kqG-5WSTezBDMybJ_bUDIHk",
    ADMIN_LOGIN="123",
    ADMIN_PASSWORD="123",
    DB_URL=f"sqlite+aiosqlite:///{DB_PATH}",
    DATABASE_URL=f"sqlite+aiosqlite:///{DB_PATH}",
    DEFAULT_BOT_PROPS=DefaultBotProperties(parse_mode="HTML"),
)

# --- внешнее API Stimul ---
STIMUL_API_URL   = "https://stimul.app/pub-api/v1/arch/set-lottery-code"
STIMUL_API_TOKEN = None  # если нужен токен — положи сюда строку

__all__ = ["settings", "STIMUL_API_URL", "STIMUL_API_TOKEN"]
