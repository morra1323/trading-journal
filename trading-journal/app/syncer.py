import ccxt
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import Trade, ExchangeAccount
from app.database import SessionLocal

SUPPORTED_EXCHANGES = ["binance", "bybit", "okx", "kraken", "gateio"]

def get_ccxt_exchange(account: ExchangeAccount):
    exchange_class = getattr(ccxt, account.exchange)
    return exchange_class({
        "apiKey": account.api_key,
        "secret": account.api_secret,
        "enableRateLimit": True,
        "timeout": 30000,
        "options": {"defaultType": "future"},
    })

def sync_account(account: ExchangeAccount, db: Session):
    """Подтягивает все закрытые сделки с биржи и сохраняет в БД"""
    try:
        exchange = get_ccxt_exchange(account)
        markets = exchange.load_markets()
        synced = 0

        # Берём все торговые пары
        symbols = [s for s in markets if "/USDT" in s][:50]  # ограничиваем для скорости

        for symbol in symbols:
            try:
                # Получаем историю сделок по символу
                raw_trades = exchange.fetch_my_trades(symbol, limit=100)
                
                for rt in raw_trades:
                    trade_id = f"{account.exchange}_{rt['id']}"
                    
                    # Пропускаем если уже есть в БД
                    exists = db.query(Trade).filter(Trade.exchange_trade_id == trade_id).first()
                    if exists:
                        continue

                    direction = "LONG" if rt["side"] == "buy" else "SHORT"
                    size = rt["cost"] if rt["cost"] else rt["amount"] * rt["price"]
                    fee = rt["fee"]["cost"] if rt.get("fee") else 0

                    trade = Trade(
                        exchange_trade_id=trade_id,
                        exchange=account.exchange,
                        symbol=symbol,
                        direction=direction,
                        entry_price=rt["price"],
                        exit_price=rt["price"],  # уточняется при закрытии
                        size=round(size, 4),
                        pnl=0,  # ccxt отдаёт P&L отдельно для фьючерсов
                        pnl_percent=0,
                        fee=round(fee, 6),
                        opened_at=datetime.utcfromtimestamp(rt["timestamp"] / 1000),
                        closed_at=datetime.utcfromtimestamp(rt["timestamp"] / 1000),
                    )
                    db.add(trade)
                    synced += 1

            except Exception:
                continue  # пропускаем пары без истории

        # Для фьючерсов — подтягиваем P&L напрямую
        if hasattr(exchange, "fetch_positions"):
            try:
                _sync_futures_pnl(exchange, account, db)
            except Exception:
                pass

        db.commit()

        # Обновляем время последней синхронизации
        account.last_sync = datetime.utcnow()
        db.commit()

        return {"status": "ok", "synced": synced}

    except ccxt.AuthenticationError:
        return {"status": "error", "message": "Неверный API ключ"}
    except ccxt.NetworkError as e:
        return {"status": "error", "message": f"Сеть: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _sync_futures_pnl(exchange, account: ExchangeAccount, db: Session):
    """Подтягивает P&L по закрытым фьючерсным позициям"""
    try:
        # fetch_closed_positions доступен не на всех биржах
        if not hasattr(exchange, "fetch_closed_positions"):
            return

        positions = exchange.fetch_closed_positions()
        for pos in positions:
            trade_id = f"{account.exchange}_fut_{pos.get('id', pos['symbol'])}_{pos.get('timestamp','')}"
            exists = db.query(Trade).filter(Trade.exchange_trade_id == trade_id).first()
            if exists:
                continue

            pnl = pos.get("realizedPnl") or pos.get("info", {}).get("realizedPnl") or 0
            size = abs(pos.get("notional") or pos.get("initialMargin", 0))
            pnl_pct = (pnl / size * 100) if size else 0
            direction = "LONG" if pos.get("side") == "long" else "SHORT"

            trade = Trade(
                exchange_trade_id=trade_id,
                exchange=account.exchange,
                symbol=pos["symbol"],
                direction=direction,
                entry_price=pos.get("entryPrice") or 0,
                exit_price=pos.get("markPrice") or 0,
                size=round(size, 4),
                pnl=round(float(pnl), 4),
                pnl_percent=round(pnl_pct, 2),
                opened_at=datetime.utcfromtimestamp(pos["timestamp"] / 1000) if pos.get("timestamp") else datetime.utcnow(),
                closed_at=datetime.utcnow(),
            )
            db.add(trade)

    except Exception:
        pass


def sync_all_accounts():
    """Запускается планировщиком — синкает все активные аккаунты"""
    db = SessionLocal()
    try:
        accounts = db.query(ExchangeAccount).filter(ExchangeAccount.is_active == 1).all()
        for account in accounts:
            sync_account(account, db)
    finally:
        db.close()
