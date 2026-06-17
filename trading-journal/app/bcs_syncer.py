"""
Синкер для БКС Trade API
Документация: https://trade-api.bcs.ru/
Токен: БКС Мир инвестиций → Профиль → Счета и тарифы → Токены API
"""
import requests
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import Trade, ExchangeAccount

BCS_API = "https://trade-api.bcs.ru/v1"

def get_bcs_token(api_token: str) -> str:
    """Получаем JWT токен по API токену"""
    try:
        r = requests.post(
            f"{BCS_API}/auth/token",
            json={"token": api_token},
            timeout=15
        )
        if r.status_code == 200:
            return r.json().get("jwt", "")
        return ""
    except Exception:
        return ""

def sync_bcs(account: ExchangeAccount, db: Session):
    """Синкаем сделки с БКС"""
    try:
        jwt = get_bcs_token(account.api_key)
        if not jwt:
            return {"status": "error", "message": "Не удалось получить JWT токен БКС"}

        headers = {"Authorization": f"Bearer {jwt}"}
        synced = 0

        # Получаем список счетов
        r = requests.get(f"{BCS_API}/accounts", headers=headers, timeout=15)
        if r.status_code != 200:
            return {"status": "error", "message": f"Ошибка получения счетов: {r.status_code}"}

        accounts = r.json().get("accounts", [])

        date_from = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")
        date_to = datetime.utcnow().strftime("%Y-%m-%d")

        for acc in accounts:
            acc_id = acc.get("id") or acc.get("agreementNumber")
            if not acc_id:
                continue

            try:
                # История сделок по счёту
                r = requests.get(
                    f"{BCS_API}/accounts/{acc_id}/trades",
                    headers=headers,
                    params={"from": date_from, "to": date_to, "limit": 200},
                    timeout=15
                )

                if r.status_code != 200:
                    continue

                trades_data = r.json().get("trades", r.json() if isinstance(r.json(), list) else [])

                for t in trades_data:
                    trade_id = f"bcs_{acc_id}_{t.get('id', t.get('tradeNo', ''))}"
                    exists = db.query(Trade).filter(Trade.exchange_trade_id == trade_id).first()
                    if exists:
                        continue

                    buysell = str(t.get("buySell") or t.get("side") or "").upper()
                    direction = "LONG" if buysell in ("B", "BUY", "1") else "SHORT"
                    price = float(t.get("price") or t.get("tradePrice") or 0)
                    qty = float(t.get("quantity") or t.get("qty") or 1)
                    size = round(price * qty, 2)

                    date_str = t.get("date") or t.get("tradeDate") or t.get("time") or ""
                    try:
                        if "T" in str(date_str):
                            trade_date = datetime.fromisoformat(str(date_str).replace("Z", "+00:00")).replace(tzinfo=None)
                        else:
                            trade_date = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
                    except Exception:
                        trade_date = datetime.utcnow()

                    symbol = t.get("symbol") or t.get("secCode") or t.get("ticker") or "Unknown"

                    trade = Trade(
                        exchange_trade_id=trade_id,
                        exchange="bcs",
                        symbol=symbol,
                        direction=direction,
                        entry_price=price,
                        exit_price=price,
                        size=size,
                        pnl=float(t.get("pnl") or t.get("profit") or 0),
                        pnl_percent=0,
                        fee=float(t.get("commission") or t.get("fee") or 0),
                        opened_at=trade_date,
                        closed_at=trade_date,
                        user_id=account.user_id,
                        account_name=f"БКС {acc_id}",
                    )
                    db.add(trade)
                    synced += 1

            except Exception:
                continue

        db.commit()
        account.last_sync = datetime.utcnow()
        db.commit()
        return {"status": "ok", "synced": synced}

    except requests.exceptions.ConnectionError:
        return {"status": "error", "message": "Нет соединения с БКС API"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
