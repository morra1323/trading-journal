from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.auth import hash_password, verify_password, create_token, decode_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter()
security = HTTPBearer(auto_error=False)

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Не авторизован")
    user_id = decode_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Неверный токен")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return user

def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    if not credentials:
        return None
    user_id = decode_token(credentials.credentials)
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()

@router.post("/register")
def register(data: dict, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data["email"]).first():
        raise HTTPException(status_code=400, detail="Email уже занят")
    if db.query(User).filter(User.username == data["username"]).first():
        raise HTTPException(status_code=400, detail="Имя пользователя занято")
    user = User(
        email=data["email"],
        username=data["username"],
        password_hash=hash_password(data["password"])
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token(user.id)
    return {"token": token, "username": user.username, "email": user.email}

@router.post("/login")
def login(data: dict, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data["email"]).first()
    if not user or not verify_password(data["password"], user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    token = create_token(user.id)
    return {"token": token, "username": user.username, "email": user.email}

@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "email": user.email}

@router.post("/change-password")
def change_password(data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(data["old_password"], user.password_hash):
        raise HTTPException(status_code=400, detail="Неверный текущий пароль")
    user.password_hash = hash_password(data["new_password"])
    db.commit()
    return {"status": "ok"}

@router.delete("/delete-account")
def delete_account(data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(data["password"], user.password_hash):
        raise HTTPException(status_code=400, detail="Неверный пароль")
    from app.models import Trade, ExchangeAccount
    db.query(Trade).filter(Trade.user_id == user.id).delete()
    db.query(ExchangeAccount).filter(ExchangeAccount.user_id == user.id).delete()
    db.delete(user)
    db.commit()
    return {"status": "deleted"}
