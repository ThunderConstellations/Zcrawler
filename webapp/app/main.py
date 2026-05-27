from __future__ import annotations
"""FastAPI endpoints and HTML views for the Zcrawler webapp."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc
from sqlalchemy.orm import Session

from webapp.app.crawler_runner import run_valpo_business_crawler
from webapp.app.db import SessionLocal, get_db, init_db
from webapp.app.models import CrawlFinding, CrawlRun, CrawlerDefinition, new_id
from webapp.app.schemas import (
    CreateRunRequest,
    CrawlerDefinitionCreate,
    CrawlerDefinitionResponse,
    CrawlRunResponse,
)

BASE_DIR = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = BASE_DIR / "webapp" / "templates"
STATIC_DIR = BASE_DIR / "webapp" / "static"

app = FastAPI(title="Zcrawler Webapp")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Ensure static directory exists
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


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

    template_key = "valpo_businesses"
    if request_body.definition_id:
        definition = db.get(CrawlerDefinition, request_body.definition_id)
        if not definition:
            raise HTTPException(status_code=404, detail="Crawler definition not found")
        template_key = definition.template_key

    run = CrawlRun(
        id=run_id,
        definition_id=request_body.definition_id,
        template_key=template_key,
        status="queued",
        error_message=None,
        reference_address=request_body.reference_address,
        city_query=request_body.city_query,
        params_json=request_body.model_dump_json(),
        output_dir=run_dir_str,
        log_path=None,
        findings_count=0,
        created_at=datetime.utcnow(),
        started_at=None,
        completed_at=None,
    )
    db.add(run)
    db.commit()

    def _bg() -> None:
        session = SessionLocal()
        try:
            run_valpo_business_crawler(run_id=run_id, request=request_body, db=session)
        finally:
            session.close()

    background_tasks.add_task(_bg)

    return {"id": run_id, "status": "queued"}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(CrawlRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/api/runs/{run_id}/findings")
def get_findings(run_id: str, db: Session = Depends(get_db)):
    run = db.get(CrawlRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    return (
        db.query(CrawlFinding)
        .filter(CrawlFinding.run_id == run_id)
        .order_by(CrawlFinding.distance_miles.asc())
        .all()
    )
