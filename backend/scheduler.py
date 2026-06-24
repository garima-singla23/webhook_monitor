# scheduler.py
# ─────────────────────────────────────────────
# APScheduler setup
# Runs health checks every 60 seconds
# Runs cleanup jobs weekly
# ─────────────────────────────────────────────

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging

logger = logging.getLogger(__name__)

# Create scheduler instance
# AsyncIOScheduler works with FastAPI's async event loop
scheduler = AsyncIOScheduler()


def start_scheduler():
    """
    Register all scheduled jobs and start scheduler.
    Called once when FastAPI app starts.
    """

    # Import here to avoid circular imports
    from services.health_checker import check_all_endpoints
    from services.retry_queue import process_retry_queue

    # ── Job 1: Health Check every 60 seconds ──
    scheduler.add_job(
        func=check_all_endpoints,
        trigger=IntervalTrigger(seconds=60),
        id="health_check",
        name="Check all endpoints",
        replace_existing=True,
        misfire_grace_time=30  # allow 30s delay before skipping
    )

    logger.info("Scheduled: health_check every 60 seconds")

    # ── Job 2: Process retry queue every 30 seconds ──
    scheduler.add_job(
        func=process_retry_queue,
        trigger=IntervalTrigger(seconds=30),
        id="retry_queue",
        name="Process webhook delivery retry queue",
        replace_existing=True,
        misfire_grace_time=15
    )

    logger.info("Scheduled: retry_queue every 30 seconds")

    # Start the scheduler
    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler():
    """Stop scheduler gracefully on app shutdown"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")


def get_scheduler_status() -> dict:
    """Get current scheduler status for health check"""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time)
        })

    return {
        "running": scheduler.running,
        "jobs": jobs
    }