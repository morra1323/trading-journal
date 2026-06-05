from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Trade, User
from app.routers.users import get_optional_user
from typing import Optional
from datetime import datetime, timedelta

router = APIRouter()

ACHIEVEMENTS = [
    {"id": "first_trade", "name": "Первая сделка", "desc": "Добавил первую сделку", "icon": "🎯", "xp": 50},
    {"id": "ten_trades", "name": "Десятка", "desc": "10 сделок в журнале", "icon": "🔟", "xp": 100},
    {"id": "fifty_trades", "name": "Полтинник", "desc": "50 сделок в журнале", "icon": "💪", "xp": 200},
    {"id": "hundred_trades", "name": "Сотня", "desc": "100 сделок в журнале", "icon": "💯", "xp": 500},
    {"id": "streak_3", "name": "На волне", "desc": "3 прибыльные сделки подряд", "icon": "🔥", "xp": 150},
    {"id": "streak_5", "name": "Огонь!", "desc": "5 прибыльных сделок подряд", "icon": "🚀", "xp": 300},
    {"id": "streak_10", "name": "Непобедимый", "desc": "10 прибыльных сделок подряд", "icon": "⚡", "xp": 1000},
    {"id": "profit_1k", "name": "Первая тысяча", "desc": "Заработал $1000 суммарно", "icon": "💰", "xp": 300},
    {"id": "profit_10k", "name": "В десятке", "desc": "Заработал $10 000 суммарно", "icon": "💎", "xp": 1000},
    {"id": "winrate_70", "name": "Снайпер", "desc": "Винрейт выше 70%", "icon": "🎯", "xp": 400},
    {"id": "pf_2", "name": "Профессионал", "desc": "Profit Factor выше 2.0", "icon": "📈", "xp": 400},
    {"id": "psychology", "name": "Психолог", "desc": "Добавил настроение к 10 сделкам", "icon": "🧠", "xp": 200},
    {"id": "no_revenge", "name": "Железные нервы", "desc": "Не торговал после 3 лоссов подряд", "icon": "🧊", "xp": 500},
]

LEVELS = [
    {"level": 1, "name": "Новичок", "min_xp": 0, "icon": "🌱"},
    {"level": 2, "name": "Стажёр", "min_xp": 200, "icon": "📚"},
    {"level": 3, "name": "Трейдер", "min_xp": 500, "icon": "📊"},
    {"level": 4, "name": "Опытный", "min_xp": 1000, "icon": "⚡"},
    {"level": 5, "name": "Профи", "min_xp": 2000, "icon": "🚀"},
    {"level": 6, "name": "Эксперт", "min_xp": 4000, "icon": "💎"},
    {"level": 7, "name": "Мастер", "min_xp": 8000, "icon": "👑"},
]

def get_current_level(xp):
    current = LEVELS[0]
    for lvl in LEVELS:
        if xp >= lvl["min_xp"]:
            current = lvl
    return current

def get_next_level(xp):
    for lvl in LEVELS:
        if xp < lvl["min_xp"]:
            return lvl
    return None

@router.get("/stats")
def get_gamification(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user)
):
    q = db.query(Trade)
    if user:
        q = q.filter(Trade.user_id == user.id)
    trades = q.order_by(Trade.closed_at).all()

    if not trades:
        return {
            "xp": 0, "level": LEVELS[0], "next_level": LEVELS[1],
            "streak": 0, "max_streak": 0,
            "achievements": [], "locked": [a["id"] for a in ACHIEVEMENTS]
        }

    pnls = [t.pnl or 0 for t in trades]
    total_pnl = sum(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    winrate = len(wins) / len(pnls) * 100 if pnls else 0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss else 0
    mood_count = sum(1 for t in trades if t.mood)

    # Стрик
    current_streak = 0
    max_streak = 0
    temp = 0
    for p in pnls:
        if p > 0:
            temp += 1
            max_streak = max(max_streak, temp)
        else:
            temp = 0
    # Текущий стрик (с конца)
    for p in reversed(pnls):
        if p > 0:
            current_streak += 1
        else:
            break

    # Проверка ачивок
    unlocked = []
    xp = 0

    checks = {
        "first_trade": len(trades) >= 1,
        "ten_trades": len(trades) >= 10,
        "fifty_trades": len(trades) >= 50,
        "hundred_trades": len(trades) >= 100,
        "streak_3": max_streak >= 3,
        "streak_5": max_streak >= 5,
        "streak_10": max_streak >= 10,
        "profit_1k": total_pnl >= 1000,
        "profit_10k": total_pnl >= 10000,
        "winrate_70": winrate >= 70 and len(trades) >= 10,
        "pf_2": profit_factor >= 2.0 and len(trades) >= 10,
        "psychology": mood_count >= 10,
        "no_revenge": True,  # упрощённо
    }

    for ach in ACHIEVEMENTS:
        if checks.get(ach["id"]):
            unlocked.append(ach)
            xp += ach["xp"]

    locked = [a["id"] for a in ACHIEVEMENTS if not checks.get(a["id"])]

    level = get_current_level(xp)
    next_level = get_next_level(xp)
    xp_to_next = (next_level["min_xp"] - xp) if next_level else 0
    xp_progress = 0
    if next_level:
        range_xp = next_level["min_xp"] - level["min_xp"]
        earned_xp = xp - level["min_xp"]
        xp_progress = round(earned_xp / range_xp * 100) if range_xp else 100

    return {
        "xp": xp,
        "level": level,
        "next_level": next_level,
        "xp_to_next": xp_to_next,
        "xp_progress": xp_progress,
        "streak": current_streak,
        "max_streak": max_streak,
        "total_trades": len(trades),
        "achievements": unlocked,
        "locked_count": len(locked),
        "all_achievements": ACHIEVEMENTS,
    }
