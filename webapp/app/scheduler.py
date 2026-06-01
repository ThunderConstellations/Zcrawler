import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.orm import Session
from webapp.app.db import SessionLocal
from webapp.app.models import CrawlerSchedule, CrawlerDefinition, CrawlRun, new_id
from webapp.app.crawler_runner import run_osm_business_crawler
from webapp.app.schemas import CreateRunRequest
from webapp.app.logging_setup import setup_logging

logger = setup_logging()

async def scheduler_loop():
    """Background loop to check and execute scheduled crawler tasks."""
    logger.info("Scheduler loop started.")
    while True:
        session = SessionLocal()
        try:
            now = datetime.utcnow()
            # Find active schedules that are due
            schedules = session.query(CrawlerSchedule).filter(
                CrawlerSchedule.is_active == True,
                (CrawlerSchedule.next_run_at <= now) | (CrawlerSchedule.next_run_at == None)
            ).all()

            for sched in schedules:
                logger.info(f"Triggering scheduled run for: {sched.name} (Definition ID: {sched.definition_id})")

                definition = session.get(CrawlerDefinition, sched.definition_id)
                if not definition:
                    logger.warning(f"Definition {sched.definition_id} not found for schedule {sched.id}")
                    sched.is_active = False # Deactivate if definition is missing
                    session.commit()
                    continue

                # Parse config to prepare request
                config = {}
                try:
                    config = json.loads(definition.config_json)
                except Exception as e:
                    logger.error(f"Failed to parse config for definition {definition.id}: {e}")

                # Create the run record and trigger the runner
                run_id = new_id()
                run_req = CreateRunRequest(
                    definition_id=definition.id,
                    reference_address=config.get("reference_address", "410 Glendale Blvd, Valparaiso, IN"),
                    city_query=config.get("city_query", "Valparaiso, Indiana, USA"),
                    enable_reverse_geocode=True,
                    max_reverse_geocode_lookups=10
                )

                # In a real app, we might want to run this in a background task properly
                # For this simple scheduler, we'll call the runner directly in a thread to not block the loop
                def _run_sync():
                    inner_session = SessionLocal()
                    try:
                        # Create the CrawlRun entry first as run_osm_business_crawler expects it
                        from webapp.app.models import CrawlRun
                        new_run = CrawlRun(
                            id=run_id,
                            definition_id=definition.id,
                            template_key=definition.template_key,
                            status="queued",
                            reference_address=run_req.reference_address,
                            city_query=run_req.city_query,
                            params_json=run_req.model_dump_json(),
                            output_dir=str(Path(__file__).resolve().parents[2] / "webapp" / "storage" / "runs" / run_id),
                            created_at=datetime.utcnow()
                        )
                        inner_session.add(new_run)
                        inner_session.commit()

                        run_osm_business_crawler(run_id=run_id, request=run_req, db=inner_session)
                    except Exception as e:
                        logger.error(f"Scheduled run {run_id} failed: {e}")
                    finally:
                        inner_session.close()

                # Offload to a thread to avoid blocking the scheduler loop
                asyncio.to_thread(_run_sync)

                # Update schedule metadata
                sched.last_run_at = now
                # Default to daily if cron parsing isn't implemented yet
                sched.next_run_at = now + timedelta(days=1)
                session.commit()

        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")
        finally:
            session.close()

        await asyncio.sleep(60) # Check every minute
