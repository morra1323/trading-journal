# Trading Journal 📈

Автоматический трейдинг-журнал — сделки подтягиваются с биржи сами.

## Быстрый старт

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API будет на http://localhost:8000
Документация: http://localhost:8000/docs

## Подключить биржу

```bash
curl -X POST http://localhost:8000/api/exchanges/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Мой Binance",
    "exchange": "binance",
    "api_key": "ВАШ_API_KEY",
    "api_secret": "ВАШ_SECRET"
  }'
```

Поддерживаются: binance, bybit, okx, kraken, gateio

## Синк вручную

```bash
curl -X POST http://localhost:8000/api/exchanges/1/sync
```

Автосинк каждые 5 минут запускается сам при старте.

## Основные эндпоинты

| Метод | URL | Описание |
|-------|-----|----------|
| GET | /api/trades/ | Все сделки |
| GET | /api/trades/stats | Статистика + аналитика |
| PATCH | /api/trades/{id} | Добавить заметку/стратегию |
| GET | /api/exchanges/ | Подключённые биржи |
| POST | /api/exchanges/ | Добавить биржу |
| POST | /api/exchanges/{id}/sync | Ручной синк |

## Структура проекта

```
trading-journal/
├── app/
│   ├── main.py          # FastAPI приложение
│   ├── database.py      # SQLite подключение
│   ├── models.py        # Таблицы БД
│   ├── syncer.py        # Логика подтягивания сделок с бирж
│   ├── scheduler.py     # Автосинк каждые 5 минут
│   └── routers/
│       ├── trades.py    # API сделок + аналитика
│       └── exchanges.py # API бирж
├── requirements.txt
└── trading_journal.db   # База данных (создаётся автоматически)
```

## Что дальше

- [ ] Фронтенд (React/Next.js)
- [ ] AI-анализ паттернов через Claude API 
- [ ] Поддержка MT4/MT5 через CSV импорт
- [ ] Авторизация пользователей (JWT)
- [ ] Деплой на VPS
