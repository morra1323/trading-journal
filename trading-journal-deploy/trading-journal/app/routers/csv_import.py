from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Trade, User
from app.routers.users import get_optional_user
from typing import Optional
import csv, io, time
from datetime import datetime

router = APIRouter()

def parse_float(val):
    try:
        return float(str(val).replace(',', '.').replace(' ', '').replace('$', ''))
    except:
        return 0.0

def parse_date(val):
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%Y %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(str(val).strip(), fmt)
        except:
            continue
    return datetime.utcnow()

def detect_format(headers):
    """Определяем формат CSV по заголовкам"""
    h = [x.lower().strip() for x in headers]
    if "реализованный pnl" in h or "realized pnl" in h or "закрытая прибыль" in h:
        return "bybit"
    if "realized profit" in h and "symbol" in h:
        return "binance_futures"
    if "price" in h and "qty" in h and "side" in h:
        return "binance_spot"
    if "сумма" in h and "инструмент" in h:
        return "tinkoff"
    if "profit" in h and "open time" in h:
        return "mt4"
    return "generic"

def parse_bybit(rows, headers, user_id):
    trades = []
    h = [x.lower().strip() for x in headers]
    for row in rows:
        r = dict(zip(h, row))
        symbol = r.get("symbol", r.get("контракт", ""))
        direction = "LONG" if "buy" in str(r.get("side", r.get("сторона", ""))).lower() else "SHORT"
        pnl = parse_float(r.get("realized pnl", r.get("реализованный pnl", r.get("закрытая прибыль", 0))))
        size = parse_float(r.get("qty", r.get("количество", r.get("объём", 0))))
        entry = parse_float(r.get("avg entry price", r.get("цена входа", 0)))
        exit_ = parse_float(r.get("avg exit price", r.get("цена выхода", 0)))
        date = parse_date(r.get("closed time", r.get("время закрытия", r.get("дата", ""))))
        if not symbol:
            continue
        trades.append(Trade(
            exchange_trade_id=f"csv_bybit_{symbol}_{int(date.timestamp())}_{int(time.time()*1000)}",
            exchange="bybit", symbol=symbol, direction=direction,
            entry_price=entry, exit_price=exit_, size=size,
            pnl=pnl, pnl_percent=round(pnl/size*100, 2) if size else 0,
            opened_at=date, closed_at=date, user_id=user_id
        ))
    return trades

def parse_binance(rows, headers, user_id):
    trades = []
    h = [x.lower().strip() for x in headers]
    for row in rows:
        r = dict(zip(h, row))
        symbol = r.get("symbol", "")
        direction = "LONG" if str(r.get("side", "")).upper() == "BUY" else "SHORT"
        price = parse_float(r.get("price", r.get("avg price", 0)))
        qty = parse_float(r.get("qty", r.get("executed qty", 0)))
        size = price * qty
        pnl = parse_float(r.get("realized profit", r.get("profit", 0)))
        date = parse_date(r.get("date(utc)", r.get("time", r.get("open time", ""))))
        if not symbol:
            continue
        trades.append(Trade(
            exchange_trade_id=f"csv_binance_{symbol}_{int(date.timestamp())}_{int(time.time()*1000)}",
            exchange="binance", symbol=symbol, direction=direction,
            entry_price=price, exit_price=price, size=round(size, 2),
            pnl=pnl, pnl_percent=round(pnl/size*100, 2) if size else 0,
            opened_at=date, closed_at=date, user_id=user_id
        ))
    return trades

def parse_tinkoff(rows, headers, user_id):
    trades = []
    h = [x.lower().strip() for x in headers]
    for row in rows:
        r = dict(zip(h, row))
        symbol = r.get("инструмент", r.get("название", ""))
        op_type = str(r.get("тип операции", r.get("операция", ""))).lower()
        if "покупка" in op_type or "buy" in op_type:
            direction = "LONG"
        else:
            direction = "SHORT"
        price = parse_float(r.get("цена", r.get("стоимость", 0)))
        qty = parse_float(r.get("количество", r.get("кол-во", 1)))
        size = parse_float(r.get("сумма", price * qty))
        pnl = parse_float(r.get("прибыль", r.get("финансовый результат", 0)))
        date = parse_date(r.get("дата", r.get("дата и время", "")))
        if not symbol:
            continue
        trades.append(Trade(
            exchange_trade_id=f"csv_tinkoff_{symbol}_{int(date.timestamp())}_{int(time.time()*1000)}",
            exchange="tinkoff", symbol=symbol, direction=direction,
            entry_price=price, exit_price=price, size=round(abs(size), 2),
            pnl=pnl, pnl_percent=0,
            opened_at=date, closed_at=date, user_id=user_id
        ))
    return trades

def parse_generic(rows, headers, user_id):
    """Универсальный парсер — пробуем угадать колонки"""
    trades = []
    h = [x.lower().strip() for x in headers]
    for row in rows:
        r = dict(zip(h, row))
        symbol = (r.get("symbol") or r.get("pair") or r.get("instrument") or
                  r.get("инструмент") or r.get("символ") or "UNKNOWN")
        direction = "LONG"
        for key in ["side", "direction", "type", "сторона", "направление"]:
            val = str(r.get(key, "")).lower()
            if val:
                direction = "LONG" if any(x in val for x in ["buy", "long", "покупка"]) else "SHORT"
                break
        pnl = 0
        for key in ["pnl", "profit", "realized pnl", "прибыль", "доход"]:
            if key in r:
                pnl = parse_float(r[key])
                break
        size = 0
        for key in ["size", "amount", "qty", "volume", "объём", "сумма"]:
            if key in r:
                size = parse_float(r[key])
                break
        date = datetime.utcnow()
        for key in ["date", "time", "closed", "дата", "время"]:
            if key in r and r[key]:
                date = parse_date(r[key])
                break
        trades.append(Trade(
            exchange_trade_id=f"csv_generic_{symbol}_{int(date.timestamp())}_{int(time.time()*1000)}",
            exchange="csv_import", symbol=symbol, direction=direction,
            entry_price=0, exit_price=0, size=abs(size),
            pnl=pnl, pnl_percent=0,
            opened_at=date, closed_at=date, user_id=user_id
        ))
    return trades


@router.post("/import")
async def import_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user)
):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Только CSV файлы")

    content = await file.read()

    # Пробуем разные кодировки
    for encoding in ['utf-8', 'utf-8-sig', 'cp1251', 'latin-1']:
        try:
            text = content.decode(encoding)
            break
        except:
            continue
    else:
        raise HTTPException(status_code=400, detail="Не удалось прочитать файл")

    # Пробуем разные разделители
    for delimiter in [',', ';', '\t']:
        try:
            reader = csv.reader(io.StringIO(text), delimiter=delimiter)
            rows = list(reader)
            if len(rows) > 1 and len(rows[0]) > 2:
                break
        except:
            continue

    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="Файл пустой или неверный формат")

    headers = rows[0]
    data_rows = rows[1:]
    user_id = user.id if user else None

    fmt = detect_format(headers)

    if fmt == "bybit":
        trades = parse_bybit(data_rows, headers, user_id)
    elif fmt in ("binance_futures", "binance_spot"):
        trades = parse_binance(data_rows, headers, user_id)
    elif fmt == "tinkoff":
        trades = parse_tinkoff(data_rows, headers, user_id)
    else:
        trades = parse_generic(data_rows, headers, user_id)

    # Сохраняем
    added = 0
    for trade in trades:
        existing = db.query(Trade).filter(Trade.exchange_trade_id == trade.exchange_trade_id).first()
        if not existing:
            db.add(trade)
            added += 1

    db.commit()
    return {
        "status": "ok",
        "format_detected": fmt,
        "total_rows": len(data_rows),
        "added": added,
        "skipped": len(data_rows) - added
    }
