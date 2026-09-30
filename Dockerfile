# GrantHub: Telegram-бот + сайт в одном контейнере
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Almaty

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core ./core
COPY telegram_bot ./telegram_bot
COPY website ./website
COPY run_all.py run_bot.py run_web.py ./

# База и логи — на постоянном диске хостинга (Railway Volume монтируется в /data)
ENV DATA_DIR=/data \
    LOGS_DIR=/data/logs \
    WEB_RUN_SCHEDULER=0

EXPOSE 8000

CMD ["python", "run_all.py"]
