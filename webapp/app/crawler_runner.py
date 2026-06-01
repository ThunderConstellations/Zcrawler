from __future__ import annotations
# Run and persist crawls for Zcrawler webapp.

import json
import subprocess
import sys
import shlex
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from webapp.app.logging_setup import setup_logging
from webapp.app.models import CrawlFinding, CrawlRun, CrawlerDefinition
from webapp.app.schemas import CreateRunRequest
from webapp.app.enrichment import extract_basic_info_from_url, generate_ai_summary

logger = setup_logging()

REPO_ROOT = Path(__file__).resolve().parents[2]
STORAGE_DIR = REPO_ROOT / "webapp" / "storage"


def _run_dir_for(run_id: str) -> Path:
    return STORAGE_DIR / "runs" / run_id


def _script_command_for_osm(request: CreateRunRequest, run_dir: Path, config: Dict[str, Any]) -> List[str]:
    script_path = REPO_ROOT / "scripts" / "osm_business_crawler.py"
    reference_address = config.get("reference_address", request.reference_address)
    city_query = config.get("city_query", request.city_query)
    categories = config.get("categories")
    radius_mi = config.get("radius_mi")
    limit = config.get("limit")

    cmd = [sys.executable, str(script_path), "--reference-address", reference_address, "--city-query", city_query, "--output-dir", str(run_dir), "--max-reverse-geocode-lookups", str(request.max_reverse_geocode_lookups)]
    if not request.enable_reverse_geocode: cmd.append("--no-reverse-geocode")
    if categories: cmd.extend(["--categories", categories])
    if radius_mi: cmd.extend(["--radius-mi", str(radius_mi)])
    if limit: cmd.extend(["--limit", str(limit)])
    return cmd


def _script_command_for_directory(run_dir: Path, config: Dict[str, Any], ai_prompt: str = None) -> List[str]:
    script_path = REPO_ROOT / "scripts" / "directory_scraper.py"
    url = config.get("url", "http://example.com")
    cmd = [sys.executable, str(script_path), "--url", url, "--output-dir", str(run_dir)]
    if ai_prompt:
        cmd.extend(["--ai-prompt", ai_prompt])
    return cmd


def _load_findings(output_dir: Path) -> List[Dict[str, Any]]:
    output_json = output_dir / "businesses.json"
    if not output_json.exists():
        logger.warning("Output JSON not found at %s", output_json)
        return []
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    return payload.get("businesses", [])


def run_osm_business_crawler(run_id: str, request: CreateRunRequest, db: Session) -> None:
    """Execute crawler and persist results."""
    run: Optional[CrawlRun] = db.get(CrawlRun, run_id)
    if run is None: raise RuntimeError(f"Run not found in DB: {run_id}")

    run_dir = _run_dir_for(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "run.log"

    config = {}
    if run.definition_id:
        definition = db.get(CrawlerDefinition, run.definition_id)
        if definition and definition.config_json:
            try: config = json.loads(definition.config_json)
            except Exception: pass

    if run.template_key in ["osm_business_crawler"]:
        cmd = _script_command_for_osm(request, run_dir, config)
    elif run.template_key == "directory_scraper":
        ai_prompt = None
        if run.definition_id:
            definition = db.get(CrawlerDefinition, run.definition_id)
            if definition:
                ai_prompt = definition.ai_prompt
        cmd = _script_command_for_directory(run_dir, config, ai_prompt=ai_prompt)
    else:
        raise RuntimeError(f"Unsupported template_key: {run.template_key}")

    run.log_path = str(log_path)
    run.started_at = datetime.utcnow()
    run.status = "running"
    db.commit()

    try:
        with log_path.open("w", encoding="utf-8") as f:
            completed = subprocess.run(cmd, cwd=REPO_ROOT, stdout=f, stderr=subprocess.STDOUT, text=True, check=False)
            exit_code = completed.returncode
        if exit_code != 0: raise RuntimeError(f"Crawler exited with code {exit_code}")

        businesses = _load_findings(run_dir)
        findings: List[CrawlFinding] = []
        for row in businesses:
            b = CrawlFinding(
                run_id=run_id, name=str(row.get("name", "")), business_type=str(row.get("business_type", "")),
                phone=str(row.get("phone", "N/A")), website=str(row.get("website", "N/A")), email=str(row.get("email", "N/A")),
                opening_hours=str(row.get("opening_hours", "N/A")), location=str(row.get("location", "")),
                latitude=float(row.get("latitude", 0.0)), longitude=float(row.get("longitude", 0.0)),
                distance_miles=float(row.get("distance_miles", 0.0)), quality_score=int(row.get("quality_score", 0)),
                source=row.get("source"),
            )
            # Enrichment
            if b.website and b.website != "N/A" and len(findings) < 5:
                en = extract_basic_info_from_url(b.website)
                b.description, b.social_links = en.get("description"), en.get("social_links")
                b.ai_summary = generate_ai_summary(b.name, b.business_type, b.description or "")
            findings.append(b)

        db.query(CrawlFinding).filter(CrawlFinding.run_id == run_id).delete()
        db.add_all(findings)
        run.findings_count, run.status, run.completed_at = len(findings), "completed", datetime.utcnow()
        db.commit()
    except Exception as exc:
        run.status, run.error_message, run.completed_at = "failed", f"{type(exc).__name__}: {exc}", datetime.utcnow()
        logger.error("Run failed: %s", exc, exc_info=True)
        db.commit()
