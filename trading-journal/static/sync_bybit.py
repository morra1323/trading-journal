"""
New Trading Era — Локальный синк с Bybit
==========================================
Запусти этот скрипт на своём компе чтобы подтянуть сделки с Bybit.
Работает через твой российский IP — никаких блокировок!

Установка:
    pip install ccxt requests

Настройка:
    1. Укажи SERVER_URL — адрес твоего журнала
    2. Укажи TOKEN — твой JWT токен из браузера (F12 → Application → localStorage → tj_token)
    3. Укажи BYBIT_API_KEY и BYBIT_SECRET — API ключи Bybit (только чтение!)

Запуск:
    python sync_bybit.py
"""

import ccxt
import requests
from datetime import datetime

# ==================== НАСТРОЙКИ ====================
SERVER_URL = "https://твой-сайт.railway.app"  # замени на свой адрес
TOKEN = "твой_jwt_токен"                        # из localStorage браузера
BYBIT_API_KEY = "твой_api_ключ"
BYBIT_SECRET = "твой_secret"
DAYS_BACK = 30  # за сколько дней тянуть сделки
# ===================================================


def get_bybit_trades():
    """Получаем сделки с Bybit"""
    exchange = ccxt.bybit({
        "apiKey": BYBIT_API_KEY,
        "secret": BYBIT_SECRET,
        "enableRateLimit": True,
        "timeout": 30000,
    })

    trades = []
    
    print("Подключаемся к Bybit...")
    
    # Фьючерсы (линейные)
    try:
        exchange.options["defaultType"] = "linear"
        closed = exchange.fetch_closed_orders(limit=200)
        print(f"  Фьючерсы: найдено {len(closed)} ордеров")
        for order in closed:
            if order.get("status") == "closed" and float(order.get("filled") or 0) > 0:
                trades.append(convert_order(order, "bybit_futures"))
    except Exception as e:
        print(f"  Фьючерсы: ошибка — {e}")

    # Спот
    try:
        exchange.options["defaultType"] = "spot"
        markets = exchange.load_markets()
        usdt_pairs = [s for s in markets if "/USDT" in s][:30]
        
        spot_count = 0
        for symbol in usdt_pairs:
            try:
                raw = exchange.fetch_my_trades(symbol, limit=50)
                for t in raw:
                    trades.append(convert_trade(t, "bybit_spot"))
                    spot_count += 1
            except Exception:
                continue
        print(f"  Спот: найдено {spot_count} сделок")
    except Exception as e:
        print(f"  Спот: ошибка — {e}")

    return trades


def convert_order(order, exchange_type):
    """Конвертируем ордер в формат журнала"""
    direction = "LONG" if order.get("side") == "buy" else "SHORT"
    price = float(order.get("average") or order.get("price") or 0)
    filled = float(order.get("filled") or 0)
    size = round(price * filled, 2)
    ts = order.get("timestamp") or order.get("lastUpdateTimestamp")
    trade_date = datetime.utcfromtimestamp(ts / 1000).isoformat() if ts else datetime.utcnow().isoformat()
    
    return {
        "exchange_trade_id": f"{exchange_type}_{order['id']}",
        "exchange": "bybit",
        "symbol": order.get("symbol", ""),
        "direction": direction,
        "entry_price": price,
        "exit_price": price,
        "size": size,
        "pnl": float(order.get("info", {}).get("cumRealisedPnl", 0) or 0),
        "pnl_percent": 0,
        "opened_at": trade_date,
        "closed_at": trade_date,
    }


def convert_trade(trade, exchange_type):
    """Конвертируем спот сделку"""
    direction = "LONG" if trade.get("side") == "buy" else "SHORT"
    price = float(trade.get("price") or 0)
    size = float(trade.get("cost") or 0)
    ts = trade.get("timestamp")
    trade_date = datetime.utcfromtimestamp(ts / 1000).isoformat() if ts else datetime.utcnow().isoformat()
    
    return {
        "exchange_trade_id": f"{exchange_type}_{trade['id']}",
        "exchange": "bybit",
        "symbol": trade.get("symbol", ""),
        "direction": direction,
        "entry_price": price,
        "exit_price": price,
        "size": round(size, 2),
        "pnl": 0,
        "pnl_percent": 0,
        "opened_at": trade_date,
        "closed_at": trade_date,
    }


def send_to_server(trades):
    """Отправляем сделки на сервер"""
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    
    added = 0
    skipped = 0
    
    print(f"\nОтправляем {len(trades)} сделок на сервер...")
    
    for trade in trades:
        try:
            r = requests.post(
                f"{SERVER_URL}/api/trades/",
                json=trade,
                headers=headers,
                timeout=10
            )
            if r.status_code == 200:
                added += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  Ошибка отправки: {e}")
            skipped += 1
    
    return added, skipped


def main():
    print("=" * 50)
    print("New Trading Era — Синк с Bybit")
    print("=" * 50)
    
    if "твой" in SERVER_URL or "твой" in TOKEN:
        print("\n❌ Заполни настройки в начале файла!")
        print("   SERVER_URL — адрес твоего журнала")
        print("   TOKEN — JWT токен из браузера")
        print("   BYBIT_API_KEY и BYBIT_SECRET — ключи Bybit")
        return
    
    # Получаем сделки с Bybit
    trades = get_bybit_trades()
    print(f"\nВсего найдено: {len(trades)} сделок")
    
    if not trades:
        print("Нет сделок для синка")
        return
    
    # Отправляем на сервер
    added, skipped = send_to_server(trades)
    
    print("\n" + "=" * 50)
    print(f"✅ Готово!")
    print(f"   Добавлено: {added} новых сделок")
    print(f"   Пропущено дублей: {skipped}")
    print("=" * 50)


if __name__ == "__main__":
    main()
