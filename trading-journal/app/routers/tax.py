from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Trade, User
from app.routers.users import get_optional_user
from typing import Optional
from datetime import datetime

router = APIRouter()

def get_tax_rate(total_profit_rub: float) -> float:
    """
    С 2025 года прогрессивная шкала НДФЛ:
    - до 2.4 млн руб → 13%
    - от 2.4 до 5 млн руб → 15%
    - от 5 до 20 млн руб → 18%
    - от 20 до 50 млн руб → 20%
    - свыше 50 млн руб → 22%
    """
    if total_profit_rub <= 2_400_000:
        return 0.13
    elif total_profit_rub <= 5_000_000:
        return 0.15
    elif total_profit_rub <= 20_000_000:
        return 0.18
    elif total_profit_rub <= 50_000_000:
        return 0.20
    else:
        return 0.22

def calc_progressive_tax(profit_rub: float) -> float:
    """Прогрессивный расчёт НДФЛ по ступеням"""
    if profit_rub <= 0:
        return 0.0
    
    tax = 0.0
    brackets = [
        (2_400_000, 0.13),
        (2_600_000, 0.15),  # 5M - 2.4M
        (15_000_000, 0.18), # 20M - 5M
        (30_000_000, 0.20), # 50M - 20M
    ]
    
    remaining = profit_rub
    for bracket_size, rate in brackets:
        if remaining <= 0:
            break
        taxable = min(remaining, bracket_size)
        tax += taxable * rate
        remaining -= taxable
    
    if remaining > 0:
        tax += remaining * 0.22
    
    return round(tax, 2)

@router.get("/summary")
def get_tax_summary(
    year: Optional[int] = None,
    usd_rate: float = 90.0,  # курс USD/RUB
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user)
):
    current_year = year or datetime.utcnow().year
    
    q = db.query(Trade)
    if user:
        q = q.filter(Trade.user_id == user.id)
    
    # Фильтруем по году
    all_trades = q.all()
    trades = [t for t in all_trades if t.closed_at and t.closed_at.year == current_year]

    if not trades:
        return {
            "year": current_year,
            "usd_rate": usd_rate,
            "total_trades": 0,
            "profit_usd": 0,
            "loss_usd": 0,
            "net_pnl_usd": 0,
            "net_pnl_rub": 0,
            "tax_rub": 0,
            "tax_usd": 0,
            "tax_rate": 0.13,
            "after_tax_usd": 0,
            "monthly": [],
            "tip": "Нет сделок за выбранный год"
        }

    pnls = [t.pnl or 0 for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    
    total_profit = sum(wins)
    total_loss = abs(sum(losses))
    net_pnl_usd = round(total_profit - total_loss, 2)
    net_pnl_rub = round(net_pnl_usd * usd_rate, 2)
    
    # Расчёт налога (только с прибыли)
    taxable_rub = max(0, net_pnl_rub)
    tax_rub = calc_progressive_tax(taxable_rub)
    tax_usd = round(tax_rub / usd_rate, 2)
    tax_rate = get_tax_rate(taxable_rub)
    after_tax_usd = round(net_pnl_usd - tax_usd, 2)

    # По месяцам
    monthly = {}
    for t in trades:
        month = t.closed_at.strftime("%Y-%m")
        if month not in monthly:
            monthly[month] = {"month": month, "pnl_usd": 0, "trades": 0}
        monthly[month]["pnl_usd"] += t.pnl or 0
        monthly[month]["trades"] += 1
    
    monthly_list = []
    for m in sorted(monthly.keys()):
        d = monthly[m]
        pnl_rub = round(d["pnl_usd"] * usd_rate, 2)
        monthly_list.append({
            "month": d["month"],
            "pnl_usd": round(d["pnl_usd"], 2),
            "pnl_rub": pnl_rub,
            "trades": d["trades"],
            "tax_rub": round(calc_progressive_tax(max(0, pnl_rub)), 2)
        })

    # Умные подсказки
    tips = []
    if net_pnl_usd > 0:
        if net_pnl_rub > 2_400_000:
            tips.append("⚠️ Твой доход превышает 2.4 млн руб — применяется ставка 15%+")
        if total_loss > 0:
            tips.append(f"💡 Убытки ({round(total_loss, 2)}$) уменьшают налоговую базу — это уже учтено")
        tips.append("📋 Если торгуешь через российского брокера (Тинькофф, Сбер) — они сами удержат налог")
        tips.append("🌍 Если торгуешь через иностранного брокера (Binance, Bybit) — нужно самостоятельно подать 3-НДФЛ до 30 апреля")
    else:
        tips.append("✅ Нет прибыли — нет налога. Убытки можно перенести на следующий год")

    return {
        "year": current_year,
        "usd_rate": usd_rate,
        "total_trades": len(trades),
        "profit_usd": round(total_profit, 2),
        "loss_usd": round(total_loss, 2),
        "net_pnl_usd": net_pnl_usd,
        "net_pnl_rub": net_pnl_rub,
        "taxable_rub": taxable_rub,
        "tax_rub": round(tax_rub, 2),
        "tax_usd": tax_usd,
        "tax_rate_pct": round(tax_rate * 100, 1),
        "after_tax_usd": after_tax_usd,
        "after_tax_rub": round(after_tax_usd * usd_rate, 2),
        "monthly": monthly_list,
        "tips": tips,
    }
