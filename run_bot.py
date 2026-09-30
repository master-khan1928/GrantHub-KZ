"""Запуск Telegram-бота:  python run_bot.py"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from telegram_bot.bot import main  # noqa: E402

if __name__ == "__main__":
    asyncio.run(main())
