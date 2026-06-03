from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Trade
import os

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

router = APIRouter()

@router.get("/analyze")
async def analyze_trades(db: Session = Depends(get_db)):
    trades = db.query(Trade).order_by(Trade.closed_at).all()
    if not trades:
        return {"analysis": "Нет сделок для анализа. Добавь хотя бы 5-10 сделок!"}

    trades_data = []
    for t in trades:
        trades_data.append({
            "symbol": t.symbol,
            "direction": t.direction,
            "pnl": t.pnl,
            "pnl_percent": t.pnl_percent,
            "strategy": t.strategy or "не указана",
            "session": t.session or "не указана",
            "date": str(t.closed_at)[:10] if t.closed_at else "неизвестно",
            "weekday": t.closed_at.strftime("%A") if t.closed_at else "неизвестно",
        })

    wins = [t for t in trades_data if (t["pnl"] or 0) > 0]
    losses = [t for t in trades_data if (t["pnl"] or 0) < 0]
    total_pnl = sum(t["pnl"] or 0 for t in trades_data)
    winrate = round(len(wins) / len(trades_data) * 100, 1) if trades_data else 0

    prompt = f"""Ты — опытный трейдинг-коуч. Проанализируй историю сделок трейдера и дай конкретные инсайты.

СТАТИСТИКА:
- Всего сделок: {len(trades_data)}
- Общий P&L: ${total_pnl:.2f}
- Винрейт: {winrate}%
- Прибыльных: {len(wins)}, убыточных: {len(losses)}

СДЕЛКИ:
{trades_data}

Дай анализ в формате:

🔍 ПАТТЕРНЫ УБЫТКОВ
(конкретно — в какое время, на каких инструментах, при каких стратегиях теряются деньги)

💪 ЧТО РАБОТАЕТ
(где трейдер зарабатывает — конкретные инструменты, стратегии, дни)

⚠️ ГЛАВНЫЕ ПРОБЛЕМЫ
(топ-3 проблемы которые нужно исправить)

🎯 КОНКРЕТНЫЕ СОВЕТЫ
(3-5 actionable шагов которые улучшат результат)

Будь конкретным, используй цифры из данных. Отвечай на русском языке."""

    def call_claude():
        import anthropic
        client = anthropic.Anthropic(
            api_key="sk-ant-api03-UqtbAHqe616PIXSQqmBHh5uDW-nb6XgFEYDDzfjamZAZYra4Qa84e_aQeMVCYoaig5xiIDTzPZTHuNQCpSiMSg-PPzYMgAA",
            timeout=120.0
        )
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text

    try:
        analysis = await run_in_threadpool(call_claude)
    except Exception as e:
        return {"analysis": f"Ошибка: {str(e)}"}

    return {"analysis": analysis, "trades_count": len(trades_data)}
