import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from webapp.app.db import SessionLocal
from webapp.app.models import CrawlerSchedule, CrawlerDefinition, CrawlRun, new_id
from webapp.app.crawler_runner import run_osm_business_crawler
from webapp.app.schemas import CreateRunRequest

async def scheduler_loop():
    """Simple background loop to check for scheduled tasks."""
    while True:
        await asyncio.sleep(60) # Check every minute
        session = SessionLocal()
        try:
            now = datetime.utcnow()
            schedules = session.query(CrawlerSchedule).filter(
                CrawlerSchedule.is_active == True,
                (CrawlerSchedule.next_run_at <= now) | (CrawlerSchedule.next_run_at == None)
            ).all()

            for sched in schedules:
                # Mock run for now
                print(f"Triggering scheduled run for: {sched.name}")

                # Update next run (simple 24h increment for demo)
                sched.last_run_at = now
                sched.next_run_at = now + timedelta(days=1)
                session.commit()

        except Exception as e:
            print(f"Scheduler error: {e}")
        finally:
            session.close()
