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
def list_definitions(request: Request, db: Session = Depends(get_db)):
    org_id = request.headers.get("X-Organization-ID")
    query = db.query(CrawlerDefinition)
    if org_id:
        query = query.filter(CrawlerDefinition.organization_id == org_id)
    return query.order_by(desc(CrawlerDefinition.created_at)).all()


@app.post("/api/definitions", response_model=CrawlerDefinitionResponse)
def create_definition(definition: CrawlerDefinitionCreate, db: Session = Depends(get_db)):
    db_def = CrawlerDefinition(
        id=new_id(),
        name=definition.name,
        description=definition.description,
        template_key=definition.template_key,
        recipe_type=definition.recipe_type,
        ai_prompt=definition.ai_prompt,
        webhook_url=definition.webhook_url,
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
    db_def.name = definition.name
    db_def.description = definition.description
    db_def.template_key = definition.template_key
    db_def.recipe_type = definition.recipe_type
    db_def.ai_prompt = definition.ai_prompt
    db_def.webhook_url = definition.webhook_url
    db_def.config_json = definition.config_json
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
    webhook_url = request_body.webhook_url
    if request_body.definition_id:
        definition = db.get(CrawlerDefinition, request_body.definition_id)
        if not definition: raise HTTPException(status_code=404, detail="Definition not found")
        template_key = definition.template_key
        webhook_url = webhook_url or definition.webhook_url

    run = CrawlRun(
        id=run_id, definition_id=request_body.definition_id, template_key=template_key,
        status="queued", reference_address=request_body.reference_address, city_query=request_body.city_query,
        webhook_url=webhook_url,
        params_json=request_body.model_dump_json(), output_dir=run_dir_str, created_at=datetime.utcnow()
    )
    db.add(run)
    db.commit()

    def _bg() -> None:
        session = SessionLocal()
        try: execute_run(run_id=run_id, request=request_body, db=session)
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
    # Run a limited version of the crawler (e.g., limit=3) and return findings
    try:
        config = json.loads(definition.config_json)
    except Exception:
        config = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        if definition.template_key == "directory_scraper":
            cmd = _script_command_for_directory(tmpdir_path, config, ai_prompt=definition.ai_prompt, limit=3)
        elif definition.template_key == "osm_business_crawler":
            # Mock a CreateRunRequest for OSM preview
            from webapp.app.schemas import CreateRunRequest
            mock_request = CreateRunRequest(
                reference_address=config.get("reference_address", "Valparaiso, IN"),
                city_query=config.get("city_query", "Valparaiso, IN")
            )
            cmd = _script_command_for_osm(mock_request, tmpdir_path, config, limit=3)
        else:
            return {"findings": [{"name": f"Preview not supported for {definition.template_key}", "business_type": "Error", "distance_miles": 0.0}]}

        try:
            # Run the command synchronously (for preview we keep it simple, though async would be better for high load)
            proc = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                 return {"findings": [{"name": f"Preview script failed (code {proc.returncode})", "business_type": "Error", "details": proc.stderr[:500]}]}

            findings = _load_findings(tmpdir_path)
            return {"findings": findings}
        except Exception as e:
            return {"findings": [{"name": f"Preview failed: {str(e)}", "business_type": "Error", "distance_miles": 0.0}]}


@app.post("/api/resume/parse")
async def parse_resume(file: UploadFile = File(...)):
    content = await file.read()
    # In a real app, use a library like PyPDF2 to extract text from PDF
    # For now, we assume text or simple extraction
    text = content.decode('utf-8', errors='ignore')
    from webapp.app.enrichment import parse_resume_with_ai
    profile = parse_resume_with_ai(text)

    if profile:
        profile_path = BASE_DIR / "webapp" / "app" / "data" / "default_profile.json"
        profile_path.write_text(json.dumps(profile, indent=2))
        return {"status": "success", "profile": profile}
    return {"status": "error", "message": "Failed to parse resume"}


@app.get("/api/runs/{run_id}/live")
def get_live_findings(run_id: str, db: Session = Depends(get_db)):
    """Return findings for a run as a live JSON API endpoint."""
    run = db.get(CrawlRun, run_id)
    if run is None: raise HTTPException(status_code=404, detail="Run not found")
    findings = db.query(CrawlFinding).filter(CrawlFinding.run_id == run_id).all()
    return {
        "run_id": run.id,
        "status": run.status,
        "findings_count": len(findings),
        "data": [
            {
                "name": f.name,
                "type": f.business_type,
                "website": f.website,
                "email": f.email,
                "phone": f.phone,
                "location": f.location,
                "ai_summary": f.ai_summary
            } for f in findings
        ]
    }


@app.get("/api/profiles")
def list_profiles():
    data_dir = BASE_DIR / "webapp" / "app" / "data"
    profiles = [p.name for p in data_dir.glob("*.json")]
    return {"profiles": profiles}

@app.post("/api/profiles/{name}")
async def save_profile(name: str, profile: Dict[str, Any]):
    data_dir = BASE_DIR / "webapp" / "app" / "data"
    profile_path = data_dir / f"{name}.json"
    profile_path.write_text(json.dumps(profile, indent=2))
    return {"status": "success"}


@app.get("/api/alerts")
def list_alerts(db: Session = Depends(get_db)):
    # Simulating alert retrieval from finding_history
    history = db.query(FindingHistory).order_by(desc(FindingHistory.created_at)).limit(10).all()
    return history

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

# --- System Settings ---

@app.get("/api/settings", response_model=List[SystemSettingResponse])
def list_settings(db: Session = Depends(get_db)):
    return db.query(SystemSetting).all()

@app.post("/api/settings", response_model=SystemSettingResponse)
def update_setting(setting: SystemSettingBase, db: Session = Depends(get_db)):
    db_setting = db.get(SystemSetting, setting.key)
    if db_setting:
        db_setting.value = setting.value
    else:
        db_setting = SystemSetting(key=setting.key, value=setting.value)
        db.add(db_setting)
    db.commit()
    db.refresh(db_setting)
    return db_setting
