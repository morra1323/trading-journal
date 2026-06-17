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
    """Подтягивает закрытые позиции с биржи"""
    try:
        exchange = get_ccxt_exchange(account)
        synced = 0

        # Пробуем получить историю закрытых позиций (фьючерсы)
        try:
            exchange.options['defaultType'] = 'linear'
            trades_data = exchange.fetch_closed_orders(limit=200)
            
            for rt in trades_data:
                if rt.get('status') != 'closed':
                    continue
                    
                trade_id = f"{account.exchange}_{rt['id']}"
                exists = db.query(Trade).filter(Trade.exchange_trade_id == trade_id).first()
                if exists:
                    continue

                direction = "LONG" if rt.get("side") == "buy" else "SHORT"
                price = float(rt.get("price") or rt.get("average") or 0)
                amount = float(rt.get("filled") or rt.get("amount") or 0)
                size = round(price * amount, 2)
                pnl = float(rt.get("info", {}).get("cumExecValue", 0) or 0)
                fee = float(rt.get("fee", {}).get("cost", 0) or 0) if rt.get("fee") else 0
                ts = rt.get("timestamp") or rt.get("lastUpdateTimestamp")
                trade_date = datetime.utcfromtimestamp(ts / 1000) if ts else datetime.utcnow()

                trade = Trade(
                    exchange_trade_id=trade_id,
                    exchange=account.exchange,
                    symbol=rt.get("symbol", ""),
                    direction=direction,
                    entry_price=price,
                    exit_price=price,
                    size=size,
                    pnl=round(pnl, 4),
                    pnl_percent=0,
                    fee=round(fee, 6),
                    opened_at=trade_date,
                    closed_at=trade_date,
                    user_id=account.user_id,
                )
                db.add(trade)
                synced += 1

        except Exception as e:
            # Если fetch_closed_orders не работает — пробуем fetch_my_trades
            try:
                exchange.options['defaultType'] = 'spot'
                markets = exchange.load_markets()
                symbols = [s for s in markets if "/USDT" in s][:20]
                
                for symbol in symbols:
                    try:
                        raw_trades = exchange.fetch_my_trades(symbol, limit=50)
                        for rt in raw_trades:
                            trade_id = f"{account.exchange}_{rt['id']}"
                            exists = db.query(Trade).filter(Trade.exchange_trade_id == trade_id).first()
                            if exists:
                                continue
                            direction = "LONG" if rt["side"] == "buy" else "SHORT"
                            size = float(rt.get("cost") or 0)
                            fee = float(rt.get("fee", {}).get("cost", 0) or 0) if rt.get("fee") else 0
                            ts = rt.get("timestamp")
                            trade_date = datetime.utcfromtimestamp(ts / 1000) if ts else datetime.utcnow()
                            trade = Trade(
                                exchange_trade_id=trade_id,
                                exchange=account.exchange,
                                symbol=symbol,
                                direction=direction,
                                entry_price=float(rt.get("price") or 0),
                                exit_price=float(rt.get("price") or 0),
                                size=round(size, 2),
                                pnl=0,
                                pnl_percent=0,
                                fee=round(fee, 6),
                                opened_at=trade_date,
                                closed_at=trade_date,
                                user_id=account.user_id,
                            )
                            db.add(trade)
                            synced += 1
                    except Exception:
                        continue
            except Exception:
                pass

        db.commit()
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
    from app.tinkoff_syncer import sync_tinkoff
    from app.bcs_syncer import sync_bcs
    from app.finam_syncer import sync_finam

    db = SessionLocal()
    try:
        accounts = db.query(ExchangeAccount).filter(ExchangeAccount.is_active == 1).all()
        for account in accounts:
            try:
                if account.exchange in ("tinkoff", "tbank"):
                    sync_tinkoff(account, db)
                elif account.exchange == "bcs":
                    sync_bcs(account, db)
                elif account.exchange == "finam":
                    sync_finam(account, db)
                elif account.exchange != "bybit":  # bybit синкается из браузера
                    sync_account(account, db)
            except Exception:
                continue
    finally:
        db.close()
