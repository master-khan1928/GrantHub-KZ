"""Запуск сайта:  python run_web.py   (адрес: http://localhost:8000)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from website.web import WEB_HOST, WEB_PORT  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("website.web:app", host=WEB_HOST, port=WEB_PORT, reload=False)
