"""
Scheduler entry point for the fully automated NSE pipeline.

Runs the complete pipeline once on startup and then every
configured interval. Configuration lives in the existing
application settings (SCHEDULER_INTERVAL_MINUTES and
SCHEDULER_MAX_PAGES).

Standalone execution:

    python -m app.scheduler.nse_scheduler
"""

from apscheduler.schedulers.blocking import BlockingScheduler

from app.core.config import settings
from app.database.database import SessionLocal
from app.services.pipeline_service import PipelineService
from app.utils.logger import logger


def run_automated_pipeline():
    """Run the full automated earnings pipeline once."""

    db = SessionLocal()

    try:
        logger.info("AUTOMATED PIPELINE STARTED")

        pipeline = PipelineService(db)

        summary = pipeline.run(max_pages=settings.SCHEDULER_MAX_PAGES)

        logger.info(
            "AUTOMATED PIPELINE COMPLETED | "
            "success: %s | "
            "companies: success=%s insufficient=%s failed=%s | "
            "duration: %ss",
            summary["success"],
            summary["companies_success"],
            summary["companies_insufficient"],
            summary["companies_failed"],
            summary["duration_seconds"],
        )

        print(
            f"PIPELINE COMPLETE | "
            f"success={summary['success']} | "
            f"companies: "
            f"success={summary['companies_success']} "
            f"insufficient={summary['companies_insufficient']} "
            f"failed={summary['companies_failed']} | "
            f"duration={summary['duration_seconds']}s"
        )

    except Exception:
        logger.exception("AUTOMATED PIPELINE FAILED")
        print("PIPELINE FAILED")

    finally:
        db.close()


def start_scheduler():
    """Start the blocking interval scheduler."""

    scheduler = BlockingScheduler()

    scheduler.add_job(
        run_automated_pipeline,
        "interval",
        minutes=settings.SCHEDULER_INTERVAL_MINUTES,
        max_instances=1,
        coalesce=True,
    )

    print("NSE Scheduler Started")
    logger.info("NSE Scheduler Started")

    run_automated_pipeline()

    scheduler.start()


if __name__ == "__main__":
    start_scheduler()