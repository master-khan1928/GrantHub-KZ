"""Запуск бота и сайта в одном процессе (для сервера):  python run_all.py

Бот слушает Telegram, сайт отвечает на PORT (Railway/Render задают его сами).
Планировщик сканирования живёт в боте, поэтому WEB_RUN_SCHEDULER оставляем 0.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from telegram_bot.bot import main as bot_main  # noqa: E402
from website.web import WEB_HOST, WEB_PORT, app  # noqa: E402


async def run_web():
    config = uvicorn.Config(app, host=WEB_HOST, port=WEB_PORT, log_level="info", loop="asyncio")
    server = uvicorn.Server(config)
    await server.serve()


async def run_bot_forever():
    """Если Telegram оборвал соединение — ждём и запускаем бота снова, сайт при этом не падает."""
    while True:
        try:
            await bot_main()
            return
        except Exception as e:  # noqa: BLE001
            logging.error(f"Бот упал: {e}. Перезапуск через 15 секунд.", exc_info=True)
            await asyncio.sleep(15)


async def main():
    tasks = [asyncio.create_task(run_web(), name="web")]
    if os.getenv("BOT_TOKEN"):
        tasks.append(asyncio.create_task(run_bot_forever(), name="bot"))
    else:
        logging.warning("BOT_TOKEN не задан — запускаю только сайт.")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
