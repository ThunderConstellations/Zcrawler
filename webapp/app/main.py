from __future__ import annotations
"""FastAPI endpoints and HTML views for the Zcrawler webapp."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc
from sqlalchemy.orm import Session

from webapp.app.crawler_runner import run_valpo_business_crawler
from webapp.app.db import SessionLocal, get_db, init_db
from webapp.app.models import CrawlFinding, CrawlRun, new_run_id
from webapp.app.schemas import CreateRunRequest

BASE_DIR = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Zcrawler Webapp")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def index(request: Any) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Any, run_id: str) -> HTMLResponse:
    return templates.TemplateResponse("run_detail.html", {"request": request, "run_id": run_id})


@app.get("/api/runs")
def list_runs(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    runs = (
        db.query(CrawlRun)
        .order_by(desc(CrawlRun.created_at))
        .limit(50)
        .all()
    )
    return [
        {
            "id": run.id,
            "template_key": run.template_key,
            "status": run.status,
            "created_at": run.created_at.isoformat(),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "reference_address": run.reference_address,
            "city_query": run.city_query,
            "findings_count": run.findings_count,
            "error_message": run.error_message,
        }
        for run in runs
    ]


@app.post("/api/runs")
def create_run(
    request_body: CreateRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    run_id = new_run_id()
    run_dir = BASE_DIR / "storage" / "runs" / run_id
    run_dir_str = str(run_dir)

    run = CrawlRun(
        id=run_id,
        template_key="valpo_businesses",
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
def get_run(run_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    run = db.get(CrawlRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "id": run.id,
        "template_key": run.template_key,
        "status": run.status,
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "reference_address": run.reference_address,
        "city_query": run.city_query,
        "findings_count": run.findings_count,
        "error_message": run.error_message,
        "output_dir": run.output_dir,
        "log_path": run.log_path,
        "params_json": run.params_json,
    }


@app.get("/api/runs/{run_id}/findings")
def get_findings(run_id: str, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    run = db.get(CrawlRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    findings = (
        db.query(CrawlFinding)
        .filter(CrawlFinding.run_id == run_id)
        .order_by(CrawlFinding.distance_miles.asc())
        .all()
    )
    return [
        {
            "id": f.id,
            "run_id": f.run_id,
            "name": f.name,
            "business_type": f.business_type,
            "phone": f.phone,
            "website": f.website,
            "email": f.email,
            "opening_hours": f.opening_hours,
            "location": f.location,
            "latitude": f.latitude,
            "longitude": f.longitude,
            "distance_miles": f.distance_miles,
            "quality_score": f.quality_score,
            "source": f.source,
            "created_at": f.created_at.isoformat(),
        }
        for f in findings
    ]
