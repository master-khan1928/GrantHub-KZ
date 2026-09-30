# Деплой GrantHub на Railway (бот + сайт, HTTPS, работает без ноутбука)

## Что подготовлено
- `Dockerfile` — один контейнер, в нём и Telegram-бот, и сайт (`run_all.py`).
- `railway.json` — сборка из Dockerfile, автоперезапуск, проверка здоровья по `/healthz`.
- База и логи пишутся в `/data` — на постоянный диск Railway (Volume), чтобы не терялись при обновлениях.
- ИИ на сервере работает через Groq (`LLM_PROVIDER=groq`): чат — openai/gpt-oss-120b, сканер — openai/gpt-oss-20b.

## Один раз: установить CLI и войти
```powershell
npm i -g @railway/cli
railway login
```

## Первый деплой (из папки проекта)
```powershell
railway init            # создать проект (имя: granthub)
railway up              # собрать и запустить
railway domain          # получить HTTPS-адрес вида granthub-xxxx.up.railway.app
```

## Переменные окружения (Railway → Variables)
| Переменная | Значение |
|---|---|
| `BOT_TOKEN` | токен бота от BotFather |
| `ADMIN_ID` | ваш Telegram id |
| `LLM_PROVIDER` | `groq` |
| `GROQ_API_KEY` | ключ с console.groq.com |
| `WEB_ADMIN_TOKEN` | любой длинный секрет для админ-панели сайта |
| `SITE_URL` | адрес из `railway domain`, например `https://granthub-xxxx.up.railway.app` |
| `SCAN_HOURS` | `8` — на бесплатном тарифе Groq одного сканирования в день достаточно |
| `TIMEZONE` | `Asia/Almaty` |
| `DATA_DIR` | `/data` (уже задано в Dockerfile) |

Задать одной командой:
```powershell
railway variables --set "LLM_PROVIDER=groq" --set "GROQ_API_KEY=..." --set "BOT_TOKEN=..." --set "ADMIN_ID=..." --set "WEB_ADMIN_TOKEN=..." --set "SCAN_HOURS=8" --set "TIMEZONE=Asia/Almaty"
```

## Постоянный диск для базы
Уже создан: том `granthub-volume` смонтирован в `/data`. При обновлениях кода база сохраняется.
Казахстанские вузы добавляются в базу автоматически при старте, остальное наполняет сканер (каждый день в 8:00).

## Текущий деплой
- Проект Railway: `granthub`, сервис `granthub`, окружение `production`.
- Адрес: https://granthub-production.up.railway.app (лендинг), /app — приложение.
- Логи: `railway logs` (работа) и `railway logs --build` (сборка).
- Важно: бот должен быть запущен только в одном месте. Пока он работает на сервере, локальный `run_bot.py` не запускайте,
  иначе Telegram выдаёт ошибку Conflict и сообщения теряются.

## Авторизация
Регистрация и вход по почте и паролю. Сессии подписываются `SESSION_SECRET` (задан локально и на сервере).
Восстановления пароля пока нет — при необходимости добавляется отправка письма.

## Обновление после правок в коде
```powershell
railway up
```

## Локально по-прежнему
```powershell
.venv\Scripts\python.exe run_web.py    # сайт
.venv\Scripts\python.exe run_bot.py    # бот
```
Локально ИИ работает через Ollama (`LLM_PROVIDER=ollama` в `.env`), на сервере — через Groq.
