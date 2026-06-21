from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Trade, User

router = APIRouter()

@router.get("/")
def get_leaderboard(db: Session = Depends(get_db), limit: int = 50):
    users = db.query(User).all()
    board = []

    for user in users:
        trades = db.query(Trade).filter(Trade.user_id == user.id).all()
        if not trades:
            continue

        pnls = [t.pnl or 0 for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        total_pnl = round(sum(pnls), 2)
        winrate = round(len(wins) / len(pnls) * 100, 1) if pnls else 0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss else 0

        # Стрик
        current_streak = 0
        for p in reversed(pnls):
            if p > 0:
                current_streak += 1
            else:
                break

        board.append({
            "username": user.username,
            "total_pnl": total_pnl,
            "winrate": winrate,
            "profit_factor": profit_factor,
            "trades": len(trades),
            "streak": current_streak,
        })

    # Сортируем по P&L
    board.sort(key=lambda x: x["total_pnl"], reverse=True)

    # Добавляем место
    for i, entry in enumerate(board):
        entry["rank"] = i + 1

    return board[:limit]
