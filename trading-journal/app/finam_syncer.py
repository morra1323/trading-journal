"""
Синкер для Финам Trade API
Документация: https://tradeapi.finam.ru/
Токен: tradeapi.finam.ru → Токены → Создать secret токен
"""
import requests
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import Trade, ExchangeAccount

FINAM_API = "https://tradeapi.finam.ru/v2"

def get_finam_jwt(secret_token: str) -> str:
    """Обмениваем secret токен на JWT"""
    try:
        r = requests.post(
            f"{FINAM_API}/auth",
            json={"secretToken": secret_token},
            timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("token") or data.get("jwt") or data.get("accessToken") or ""
        return ""
    except Exception:
        return ""

def sync_finam(account: ExchangeAccount, db: Session):
    """Синкаем сделки с Финам"""
    try:
        jwt = get_finam_jwt(account.api_key)
        if not jwt:
            return {"status": "error", "message": "Не удалось получить JWT токен Финам. Проверь secret токен."}

        headers = {
            "Authorization": f"Bearer {jwt}",
            "Content-Type": "application/json"
        }
        synced = 0

        # Получаем список клиентских ID
        r = requests.get(f"{FINAM_API}/client/accounts", headers=headers, timeout=15)
        if r.status_code != 200:
            return {"status": "error", "message": f"Ошибка авторизации Финам: {r.status_code}"}

        accounts_data = r.json()
        client_ids = []

        if isinstance(accounts_data, list):
            client_ids = [a.get("clientId") or a.get("id") for a in accounts_data if a.get("clientId") or a.get("id")]
        elif isinstance(accounts_data, dict):
            clients = accounts_data.get("clients") or accounts_data.get("accounts") or []
            client_ids = [a.get("clientId") or a.get("id") for a in clients if a.get("clientId") or a.get("id")]

        if not client_ids:
            client_ids = ["default"]

        date_from = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%dT00:00:00")
        date_to = datetime.utcnow().strftime("%Y-%m-%dT23:59:59")

        for client_id in client_ids:
            try:
                # История сделок
                r = requests.get(
                    f"{FINAM_API}/client/{client_id}/trades",
                    headers=headers,
                    params={
                        "from": date_from,
                        "to": date_to,
                        "limit": 500
                    },
                    timeout=15
                )

                if r.status_code != 200:
                    continue

                data = r.json()
                trades_list = data if isinstance(data, list) else data.get("trades", data.get("items", []))

                for t in trades_list:
                    trade_id = f"finam_{client_id}_{t.get('tradeNo') or t.get('id') or t.get('orderId', '')}"
                    exists = db.query(Trade).filter(Trade.exchange_trade_id == trade_id).first()
                    if exists:
                        continue

                    buysell = str(t.get("buySell") or t.get("side") or t.get("operation") or "").upper()
                    direction = "LONG" if buysell in ("B", "BUY", "1", "BUY_OPERATION") else "SHORT"
                    price = float(t.get("price") or t.get("tradePrice") or 0)
                    qty = float(t.get("quantity") or t.get("qty") or 1)
                    size = round(price * qty, 2)

                    date_str = t.get("tradeTime") or t.get("date") or t.get("time") or ""
                    try:
                        if "T" in str(date_str):
                            trade_date = datetime.fromisoformat(str(date_str).replace("Z", "+00:00")).replace(tzinfo=None)
                        else:
                            trade_date = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
                    except Exception:
                        trade_date = datetime.utcnow()

                    symbol = (t.get("secCode") or t.get("symbol") or t.get("ticker") or
                             t.get("instrumentCode") or "Unknown")

                    trade = Trade(
                        exchange_trade_id=trade_id,
                        exchange="finam",
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
                        account_name=f"Финам {client_id}",
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
        return {"status": "error", "message": "Нет соединения с Финам API"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
