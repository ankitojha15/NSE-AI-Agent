from apscheduler.schedulers.blocking import BlockingScheduler

from app.database.database import SessionLocal
from app.services.nse_service import NseService
from app.utils.logger import logger


def sync_nse_results():

    db = SessionLocal()

    try:
        logger.info("NSE sync started")

        service = NseService()

        new_records = service.sync_integrated_filings(db)

        logger.info(
            f"NSE sync completed | "
            f"new records: {len(new_records)}"
        )

        print(
            f"NSE SYNC COMPLETE | "
            f"NEW RECORDS: {len(new_records)}"
        )

    except Exception:
        logger.exception("NSE sync failed")

    finally:
        db.close()


scheduler = BlockingScheduler()

scheduler.add_job(
    sync_nse_results,
    "interval",
    minutes=10,
    max_instances=1,
    coalesce=True
)

print("NSE Scheduler Started")
logger.info("NSE Scheduler Started")

sync_nse_results()

scheduler.start()