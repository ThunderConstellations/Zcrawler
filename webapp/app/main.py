from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc
from sqlalchemy.orm import Session

from webapp.app.crawler_runner import execute_run, _script_command_for_osm, _script_command_for_directory, _load_findings
from webapp.app.db import SessionLocal, get_db, init_db
from webapp.app.models import CrawlFinding, CrawlRun, CrawlerDefinition, CrawlerSchedule, SystemSetting, FindingHistory, new_id
from webapp.app.schemas import (
    CreateRunRequest,
    CrawlerDefinitionCreate,
    CrawlerDefinitionResponse,
    CrawlRunResponse, CrawlerScheduleCreate, CrawlerScheduleResponse,
    SystemSettingBase, SystemSettingResponse,
)
from webapp.app.scheduler import scheduler_loop

BASE_DIR = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = BASE_DIR / "webapp" / "templates"
STATIC_DIR = BASE_DIR / "webapp" / "static"

app = FastAPI(title="Zcrawler Webapp")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    asyncio.create_task(scheduler_loop())

@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html", context={})

@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: str) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="run_detail.html", context={"run_id": run_id})

# --- Definitions ---
@app.get("/api/definitions", response_model=List[CrawlerDefinitionResponse])
def list_definitions(request: Request, db: Session = Depends(get_db)):
    org_id = request.headers.get("X-Organization-ID")
    query = db.query(CrawlerDefinition)
    if org_id: query = query.filter(CrawlerDefinition.organization_id == org_id)
    return query.order_by(desc(CrawlerDefinition.created_at)).all()

@app.post("/api/definitions", response_model=CrawlerDefinitionResponse)
def create_definition(request: Request, definition: CrawlerDefinitionCreate, db: Session = Depends(get_db)):
    org_id = request.headers.get("X-Organization-ID")
    db_def = CrawlerDefinition(
        id=new_id(), name=definition.name, description=definition.description, template_key=definition.template_key,
        recipe_type=definition.recipe_type, ai_prompt=definition.ai_prompt, webhook_url=definition.webhook_url,
        config_json=definition.config_json, organization_id=org_id, is_template=1 if definition.is_template else 0
    )
    db.add(db_def)
    db.commit()
    db.refresh(db_def)
    return db_def

@app.delete("/api/definitions/{definition_id}")
def delete_definition(definition_id: str, db: Session = Depends(get_db)):
    db_def = db.get(CrawlerDefinition, definition_id)
    if not db_def: raise HTTPException(status_code=404, detail="Not found")
    db.delete(db_def)
    db.commit()
    return {"status": "success"}

# --- Runs ---
@app.get("/api/runs", response_model=List[CrawlRunResponse])
def list_runs(request: Request, db: Session = Depends(get_db)):
    org_id = request.headers.get("X-Organization-ID")
    query = db.query(CrawlRun)
    if org_id: query = query.filter(CrawlRun.organization_id == org_id)
    return query.order_by(desc(CrawlRun.created_at)).limit(50).all()

@app.post("/api/runs")
def create_run(request: Request, request_body: CreateRunRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    run_id = new_id()
    run_dir = BASE_DIR / "webapp" / "storage" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    org_id = request.headers.get("X-Organization-ID")
    template_key = "osm_business_crawler"
    if request_body.definition_id:
        definition = db.get(CrawlerDefinition, request_body.definition_id)
        if definition: template_key = definition.template_key
    run = CrawlRun(
        id=run_id, definition_id=request_body.definition_id, template_key=template_key,
        status="queued", reference_address=request_body.reference_address, city_query=request_body.city_query,
        organization_id=org_id, params_json=request_body.model_dump_json(), output_dir=str(run_dir), created_at=datetime.utcnow()
    )
    db.add(run)
    db.commit()
    def _bg():
        session = SessionLocal()
        try: execute_run(run_id=run_id, request=request_body, db=session)
        finally: session.close()
    background_tasks.add_task(_bg)
    return {"id": run_id, "status": "queued"}

@app.get("/api/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(CrawlRun, run_id)
    if not run: raise HTTPException(status_code=404, detail="Not found")
    return run

@app.get("/api/runs/{run_id}/findings")
def get_findings(run_id: str, db: Session = Depends(get_db)):
    return db.query(CrawlFinding).filter(CrawlFinding.run_id == run_id).order_by(CrawlFinding.distance_miles.asc()).all()

@app.get("/api/runs/{run_id}/logs", response_class=PlainTextResponse)
def get_logs(run_id: str, db: Session = Depends(get_db)):
    run = db.get(CrawlRun, run_id)
    if not run or not run.log_path or not os.path.exists(run.log_path): return "Log unavailable."
    with open(run.log_path, "r") as f: return f.read()



@app.get("/api/runs/{run_id}/report")
def get_mission_report(run_id: str, db: Session = Depends(get_db)):
    run = db.get(CrawlRun, run_id)
    if not run: raise HTTPException(404)
    findings = db.query(CrawlFinding).filter(CrawlFinding.run_id == run_id).all()
    types = list(set([f.business_type for f in findings]))[:4]

    # Dynamic report generation
    summary = f"Neural reconnaissance of geospatial sector {run.city_query} complete. Autonomous swarm identified {len(findings)} verified intelligence nodes. Dominant signatures include {', '.join(types)}. Mission integrity nominal."
    if not findings:
        summary = "Mission cycle active. Swarm establishes initial telemetry link. Node discovery in progress."

    return {
        "summary": summary,
        "integrity": "SECURED" if run.status == "completed" else "ACTIVE",
        "last_sync": datetime.utcnow().isoformat()
    }


@app.get("/api/runs/{run_id}/live")
def get_live(run_id: str, db: Session = Depends(get_db)):
    run = db.get(CrawlRun, run_id)
    if not run: raise HTTPException(404)
    findings = db.query(CrawlFinding).filter(CrawlFinding.run_id == run_id).all()
    return {"run_id": run.id, "status": run.status, "data": [f.__dict__ for f in findings]}

# --- AI Profile ---
@app.post("/api/resume/parse")
async def parse_resume(file: UploadFile = File(...)):
    content = await file.read()
    from webapp.app.enrichment import parse_resume_with_ai
    profile = parse_resume_with_ai(content.decode('utf-8', errors='ignore'))
    if profile:
        Path("webapp/app/data/default_profile.json").write_text(json.dumps(profile, indent=2))
        return {"status": "success", "profile": profile}
    return {"status": "error"}

@app.get("/api/profiles")
def list_profiles():
    return {"profiles": [p.name for p in Path("webapp/app/data").glob("*.json")]}

# --- Settings ---
@app.get("/api/settings", response_model=List[SystemSettingResponse])
def get_settings(db: Session = Depends(get_db)):
    return db.query(SystemSetting).all()

@app.post("/api/settings")
def update_setting(setting: SystemSettingBase, db: Session = Depends(get_db)):
    db_s = db.get(SystemSetting, setting.key)
    if db_s: db_s.value = setting.value
    else:
        db_s = SystemSetting(key=setting.key, value=setting.value)
        db.add(db_s)
    db.commit()
    return db_s
