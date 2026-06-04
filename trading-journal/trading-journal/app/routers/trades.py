from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import Trade, User
from app.routers.users import get_optional_user

router = APIRouter()

def filter_by_user(q, user):
    if user:
        return q.filter(Trade.user_id == user.id)
    return q

@router.get("/")
def get_trades(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
    exchange: Optional[str] = None,
    symbol: Optional[str] = None,
    direction: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = 0
):
    q = filter_by_user(db.query(Trade), user)
    if exchange: q = q.filter(Trade.exchange == exchange)
    if symbol:   q = q.filter(Trade.symbol.ilike(f"%{symbol}%"))
    if direction: q = q.filter(Trade.direction == direction)
    return q.order_by(Trade.closed_at.desc()).offset(offset).limit(limit).all()

@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
    exchange: Optional[str] = None
):
    q = filter_by_user(db.query(Trade), user)
    if exchange: q = q.filter(Trade.exchange == exchange)
    trades = q.all()

    if not trades:
        return {"total_trades": 0}

    pnls = [t.pnl for t in trades if t.pnl is not None]
    wins  = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total_pnl = round(sum(pnls), 2)
    winrate = round(len(wins) / len(pnls) * 100, 1) if pnls else 0
    avg_win  = round(sum(wins) / len(wins), 2) if wins else 0
    avg_loss = round(sum(losses) / len(losses), 2) if losses else 0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss else 0

    cumulative = 0; peak = 0; max_drawdown = 0
    for p in pnls:
        cumulative += p
        if cumulative > peak: peak = cumulative
        dd = peak - cumulative
        if dd > max_drawdown: max_drawdown = dd

    by_weekday = {}
    for t in trades:
        if t.closed_at:
            day = t.closed_at.strftime("%A")
            by_weekday[day] = by_weekday.get(day, 0) + (t.pnl or 0)

    by_symbol = {}
    for t in trades:
        by_symbol[t.symbol] = by_symbol.get(t.symbol, 0) + (t.pnl or 0)
    by_symbol = {k: round(v, 2) for k, v in sorted(by_symbol.items(), key=lambda x: x[1], reverse=True)}

    by_strategy = {}
    for t in trades:
        s = t.strategy or "Без стратегии"
        by_strategy[s] = by_strategy.get(s, 0) + (t.pnl or 0)

    # По настроению
    by_mood = {}
    for t in trades:
        m = t.mood or "не указано"
        if m not in by_mood:
            by_mood[m] = {"pnl": 0, "count": 0, "wins": 0}
        by_mood[m]["pnl"] += t.pnl or 0
        by_mood[m]["count"] += 1
        if (t.pnl or 0) > 0:
            by_mood[m]["wins"] += 1
    for m in by_mood:
        by_mood[m]["pnl"] = round(by_mood[m]["pnl"], 2)
        by_mood[m]["winrate"] = round(by_mood[m]["wins"] / by_mood[m]["count"] * 100, 1)

    ordered = sorted(trades, key=lambda t: t.closed_at or t.created_at)
    cum = 0
    equity_curve = []
    for t in ordered:
        cum += t.pnl or 0
        equity_curve.append({"date": str(t.closed_at)[:10], "symbol": t.symbol, "pnl": round(cum, 2)})

    return {
        "total_trades": len(trades), "total_pnl": total_pnl, "winrate": winrate,
        "avg_win": avg_win, "avg_loss": avg_loss, "profit_factor": profit_factor,
        "max_drawdown": round(max_drawdown, 2), "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2), "by_symbol": by_symbol,
        "by_weekday": {k: round(v, 2) for k, v in by_weekday.items()},
        "by_strategy": {k: round(v, 2) for k, v in by_strategy.items()},
        "by_mood": by_mood,
        "equity_curve": equity_curve,
    }

@router.post("/")
def add_trade(data: dict, db: Session = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    import time
    trade = Trade(
        user_id=user.id if user else None,
        exchange_trade_id=data.get("exchange_trade_id", f"manual_{int(time.time())}"),
        exchange=data.get("exchange", "manual"),
        symbol=data["symbol"], direction=data["direction"],
        entry_price=data["entry_price"], exit_price=data["exit_price"],
        size=data["size"], pnl=data.get("pnl", 0), pnl_percent=data.get("pnl_percent", 0),
        opened_at=data.get("opened_at"), closed_at=data.get("closed_at"),
        strategy=data.get("strategy"), note=data.get("note"),
    )
    db.add(trade); db.commit(); db.refresh(trade)
    return trade

@router.patch("/{trade_id}")
def update_trade(trade_id: int, data: dict, db: Session = Depends(get_db)):
    trade = db.query(Trade).filter(Trade.id == trade_id).first()
    if not trade: return {"error": "Сделка не найдена"}
    for key in ["strategy", "session", "note"]:
        if key in data: setattr(trade, key, data[key])
    db.commit()
    return trade

@router.delete("/{trade_id}")
def delete_trade(trade_id: int, db: Session = Depends(get_db)):
    trade = db.query(Trade).filter(Trade.id == trade_id).first()
    if trade: db.delete(trade); db.commit()
    return {"status": "deleted"}
