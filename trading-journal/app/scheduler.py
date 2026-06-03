from apscheduler.schedulers.background import BackgroundScheduler
from app.syncer import sync_all_accounts

scheduler = BackgroundScheduler()

def start_scheduler():
    scheduler.add_job(sync_all_accounts, "interval", minutes=5, id="sync_trades", next_run_time=None)
    scheduler.start()
    print("Планировщик запущен — синк каждые 5 минут")
