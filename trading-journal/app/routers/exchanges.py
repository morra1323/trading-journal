from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ExchangeAccount, User
from app.syncer import sync_account, SUPPORTED_EXCHANGES
from app.tinkoff_syncer import sync_tinkoff
from app.routers.users import get_optional_user
from typing import Optional

router = APIRouter()

TINKOFF_EXCHANGES = ["tinkoff", "tbank"]
ALL_EXCHANGES = SUPPORTED_EXCHANGES + TINKOFF_EXCHANGES

@router.get("/supported")
def get_supported():
    return {
        "exchanges": SUPPORTED_EXCHANGES,
        "russian_brokers": TINKOFF_EXCHANGES
    }

@router.get("/")
def get_accounts(db: Session = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    q = db.query(ExchangeAccount)
    if user:
        q = q.filter(ExchangeAccount.user_id == user.id)
    accounts = q.all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "exchange": a.exchange,
            "api_key": a.api_key[:6] + "****",
            "is_active": a.is_active,
            "last_sync": a.last_sync,
        }
        for a in accounts
    ]

@router.post("/")
def add_account(data: dict, db: Session = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    account = ExchangeAccount(
        name=data.get("name", data["exchange"]),
        exchange=data["exchange"],
        api_key=data["api_key"],
        api_secret=data.get("api_secret", ""),
        user_id=user.id if user else None,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return {"status": "added", "id": account.id}

@router.post("/{account_id}/sync")
def manual_sync(account_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    account = db.query(ExchangeAccount).filter(ExchangeAccount.id == account_id).first()
    if not account:
        return {"error": "Аккаунт не найден"}

    # Выбираем синкер в зависимости от биржи
    if account.exchange in TINKOFF_EXCHANGES:
        background_tasks.add_task(sync_tinkoff, account, db)
    else:
        background_tasks.add_task(sync_account, account, db)

    return {"status": "sync started"}

@router.delete("/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.query(ExchangeAccount).filter(ExchangeAccount.id == account_id).first()
    if account:
        db.delete(account)
        db.commit()
    return {"status": "deleted"}
