from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.database import engine, Base
from app.routers import trades, exchanges, ai, users, csv_import
from app.scheduler import start_scheduler
import os

Base.metadata.create_all(bind=engine)

app = FastAPI(title="New Trading Era API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, prefix="/api/auth", tags=["auth"])
app.include_router(trades.router, prefix="/api/trades", tags=["trades"])
app.include_router(exchanges.router, prefix="/api/exchanges", tags=["exchanges"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(csv_import.router, prefix="/api/csv", tags=["csv"])

@app.on_event("startup")
def startup():
    start_scheduler()

@app.get("/")
def landing():
    return FileResponse("landing/index.html")

@app.get("/app")
def app_page():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
