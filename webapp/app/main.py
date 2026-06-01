from __future__ import annotations
"""FastAPI endpoints and HTML views for the Zcrawler webapp."""

import shutil
import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc
from sqlalchemy.orm import Session

from webapp.app.crawler_runner import run_osm_business_crawler
from webapp.app.db import SessionLocal, get_db, init_db
from webapp.app.models import CrawlFinding, CrawlRun, CrawlerDefinition, CrawlerSchedule, new_id
from webapp.app.schemas import (
    CreateRunRequest,
    CrawlerDefinitionCreate,
    CrawlerDefinitionResponse,
    CrawlRunResponse, CrawlerScheduleCreate, CrawlerScheduleResponse,
)
from webapp.app.scheduler import scheduler_loop

BASE_DIR = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = BASE_DIR / "webapp" / "templates"
STATIC_DIR = BASE_DIR / "webapp" / "static"

app = FastAPI(title="Zcrawler Webapp")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Ensure static directory exists
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    # Start scheduler in background
    asyncio.create_task(scheduler_loop())


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: str) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="run_detail.html", context={"run_id": run_id})


# --- Crawler Definitions ---

@app.get("/api/definitions", response_model=List[CrawlerDefinitionResponse])
def list_definitions(db: Session = Depends(get_db)):
    return db.query(CrawlerDefinition).order_by(desc(CrawlerDefinition.created_at)).all()


@app.post("/api/definitions", response_model=CrawlerDefinitionResponse)
def create_definition(definition: CrawlerDefinitionCreate, db: Session = Depends(get_db)):
    db_def = CrawlerDefinition(
        id=new_id(),
        name=definition.name,
        description=definition.description,
        template_key=definition.template_key,
        config_json=definition.config_json,
    )
    db.add(db_def)
    db.commit()
    db.refresh(db_def)
    return db_def

@app.put("/api/definitions/{definition_id}", response_model=CrawlerDefinitionResponse)
def update_definition(definition_id: str, definition: CrawlerDefinitionCreate, db: Session = Depends(get_db)):
    db_def = db.get(CrawlerDefinition, definition_id)
    if not db_def:
        raise HTTPException(status_code=404, detail="Definition not found")
    db_def.name, db_def.description, db_def.template_key, db_def.config_json = definition.name, definition.description, definition.template_key, definition.config_json
    db.commit()
    db.refresh(db_def)
    return db_def

@app.delete("/api/definitions/{definition_id}")
def delete_definition(definition_id: str, db: Session = Depends(get_db)):
    db_def = db.get(CrawlerDefinition, definition_id)
    if not db_def: raise HTTPException(status_code=404, detail="Definition not found")
    db.delete(db_def)
    db.commit()
    return {"status": "success"}


# --- Crawl Runs ---

@app.get("/api/runs", response_model=List[CrawlRunResponse])
def list_runs(db: Session = Depends(get_db)):
    return db.query(CrawlRun).order_by(desc(CrawlRun.created_at)).limit(50).all()


@app.post("/api/runs")
def create_run(
    request_body: CreateRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    run_id = new_id()
    run_dir = BASE_DIR / "webapp" / "storage" / "runs" / run_id
    run_dir_str = str(run_dir)

    template_key = "osm_business_crawler"
    if request_body.definition_id:
        definition = db.get(CrawlerDefinition, request_body.definition_id)
        if not definition: raise HTTPException(status_code=404, detail="Definition not found")
        template_key = definition.template_key

    run = CrawlRun(
        id=run_id, definition_id=request_body.definition_id, template_key=template_key,
        status="queued", reference_address=request_body.reference_address, city_query=request_body.city_query,
        params_json=request_body.model_dump_json(), output_dir=run_dir_str, created_at=datetime.utcnow()
    )
    db.add(run)
    db.commit()

    def _bg() -> None:
        session = SessionLocal()
        try: run_osm_business_crawler(run_id=run_id, request=request_body, db=session)
        finally: session.close()

    background_tasks.add_task(_bg)
    return {"id": run_id, "status": "queued"}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(CrawlRun, run_id)
    if run is None: raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/api/runs/{run_id}/logs", response_class=PlainTextResponse)
def get_run_logs(run_id: str, db: Session = Depends(get_db)):
    run = db.get(CrawlRun, run_id)
    if not run: raise HTTPException(status_code=404, detail="Run not found")
    if not run.log_path or not os.path.exists(run.log_path): return "Log file not found."
    with open(run.log_path, "r", encoding="utf-8") as f: return f.read()


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(CrawlRun, run_id)
    if not run: raise HTTPException(status_code=404, detail="Run not found")
    if run.output_dir and Path(run.output_dir).exists(): shutil.rmtree(run.output_dir, ignore_errors=True)
    db.delete(run)
    db.commit()
    return {"status": "success"}


@app.get("/api/runs/{run_id}/findings")
def get_findings(run_id: str, db: Session = Depends(get_db)):
    run = db.get(CrawlRun, run_id)
    if run is None: raise HTTPException(status_code=404, detail="Run not found")
    return db.query(CrawlFinding).filter(CrawlFinding.run_id == run_id).order_by(CrawlFinding.distance_miles.asc()).all()

@app.post("/api/preview")
async def preview_crawler(definition: CrawlerDefinitionCreate):
    """Temporary preview of a crawler without creating a full run."""
    # This is a simplified preview that just runs the first part of a crawl
    # or returns mock data based on the template
    if definition.template_key == "directory_scraper":
        config = json.loads(definition.config_json)
        url = config.get("url", "http://example.com")
        # In a real app, we might call the scraper script with a --preview flag
        return {"findings": [{"name": f"Preview Result from {url}", "business_type": "Preview", "distance_miles": 0.0}]}
    else:
        return {"findings": [{"name": "OSM Preview Item", "business_type": "OSM", "distance_miles": 1.0}]}

# --- Schedules ---

@app.get("/api/schedules", response_model=List[CrawlerScheduleResponse])
def list_schedules(db: Session = Depends(get_db)):
    return db.query(CrawlerSchedule).all()

@app.post("/api/schedules", response_model=CrawlerScheduleResponse)
def create_schedule(schedule: CrawlerScheduleCreate, db: Session = Depends(get_db)):
    db_sched = CrawlerSchedule(
        id=new_id(),
        definition_id=schedule.definition_id,
        name=schedule.name,
        cron_expr=schedule.cron_expr,
        is_active=1 if schedule.is_active else 0,
    )
    db.add(db_sched)
    db.commit()
    db.refresh(db_sched)
    return db_sched

@app.delete("/api/schedules/{schedule_id}")
def delete_schedule(schedule_id: str, db: Session = Depends(get_db)):
    db_sched = db.get(CrawlerSchedule, schedule_id)
    if not db_sched: raise HTTPException(status_code=404, detail="Schedule not found")
    db.delete(db_sched)
    db.commit()
    return {"status": "success"}
