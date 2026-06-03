"""
Синкер для Тинькофф Инвестиции (T-Invest API)
Токен получить: https://www.tbank.ru/invest/settings/api/
"""
import requests
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import Trade, ExchangeAccount

TINKOFF_API = "https://invest-public-api.tinkoff.ru/rest"

def get_tinkoff_headers(token: str):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

def sync_tinkoff(account: ExchangeAccount, db: Session):
    """Подтягивает закрытые сделки из Тинькофф"""
    try:
        headers = get_tinkoff_headers(account.api_key)

        # Получаем список счетов пользователя
        r = requests.post(f"{TINKOFF_API}/tinkoff.public.invest.api.contract.v1.UsersService/GetAccounts",
                         headers=headers, json={}, timeout=15)
        if r.status_code != 200:
            return {"status": "error", "message": f"Ошибка авторизации: {r.status_code}"}

        accounts_data = r.json().get("accounts", [])
        if not accounts_data:
            return {"status": "error", "message": "Нет счетов"}

        synced = 0
        now = datetime.utcnow()
        from_date = (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
        to_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        for acc in accounts_data:
            acc_id = acc["id"]

            # Получаем историю операций
            r = requests.post(
                f"{TINKOFF_API}/tinkoff.public.invest.api.contract.v1.OperationsService/GetOperationsByCursor",
                headers=headers,
                json={
                    "accountId": acc_id,
                    "from": from_date,
                    "to": to_date,
                    "operationTypes": ["OPERATION_TYPE_BUY", "OPERATION_TYPE_SELL"],
                    "state": "OPERATION_STATE_EXECUTED",
                    "limit": 100,
                },
                timeout=15
            )

            if r.status_code != 200:
                continue

            operations = r.json().get("items", [])

            for op in operations:
                trade_id = f"tinkoff_{op['id']}"
                exists = db.query(Trade).filter(Trade.exchange_trade_id == trade_id).first()
                if exists:
                    continue

                op_type = op.get("type", "")
                direction = "LONG" if "BUY" in op_type else "SHORT"

                # Цена и сумма
                price = _parse_money(op.get("price", {}))
                payment = abs(_parse_money(op.get("payment", {})))
                quantity = op.get("quantity", 1)
                size = payment if payment > 0 else price * quantity

                # P&L для продаж
                pnl = _parse_money(op.get("payment", {})) if "SELL" in op_type else 0

                # Дата
                date_str = op.get("date", "")
                try:
                    trade_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                except Exception:
                    trade_date = datetime.utcnow()

                # Название инструмента
                symbol = op.get("name") or op.get("figi") or "Unknown"

                trade = Trade(
                    exchange_trade_id=trade_id,
                    exchange="tinkoff",
                    symbol=symbol,
                    direction=direction,
                    entry_price=price,
                    exit_price=price,
                    size=round(size, 2),
                    pnl=round(pnl, 2),
                    pnl_percent=0,
                    fee=abs(_parse_money(op.get("commission", {}))),
                    opened_at=trade_date,
                    closed_at=trade_date,
                    user_id=account.user_id,
                )
                db.add(trade)
                synced += 1

        db.commit()
        account.last_sync = datetime.utcnow()
        db.commit()

        return {"status": "ok", "synced": synced}

    except requests.exceptions.ConnectionError:
        return {"status": "error", "message": "Нет соединения с T-Invest API"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _parse_money(money_obj: dict) -> float:
    """Конвертирует объект MoneyValue из API в float"""
    if not money_obj:
        return 0.0
    units = int(money_obj.get("units", 0))
    nano = int(money_obj.get("nano", 0))
    return units + nano / 1_000_000_000
