from __future__ import annotations
# Run and persist crawls for Zcrawler webapp.

# pylint: disable=import-error

from datetime import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from webapp.app.logging_setup import setup_logging
from webapp.app.models import CrawlFinding, CrawlRun
from webapp.app.schemas import CreateRunRequest

logger = setup_logging()

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_dir_for(run_id: str) -> Path:
    return REPO_ROOT / "webapp" / "storage" / "runs" / run_id


def _script_command_for_valpo(request: CreateRunRequest, run_dir: Path) -> List[str]:
    script_path = REPO_ROOT / "scripts" / "valpo_business_crawler.py"
    cmd = [
        sys.executable,
        str(script_path),
        "--reference-address",
        request.reference_address,
        "--city-query",
        request.city_query,
        "--output-dir",
        str(run_dir),
        "--max-reverse-geocode-lookups",
        str(request.max_reverse_geocode_lookups),
    ]
    if not request.enable_reverse_geocode:
        cmd.append("--no-reverse-geocode")
    return cmd


def _load_findings(output_dir: Path) -> List[Dict[str, Any]]:
    output_json = output_dir / "valparaiso_businesses.json"
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    return payload.get("businesses", [])


def run_valpo_business_crawler(run_id: str, request: CreateRunRequest, db: Session) -> None:
    """Execute the local Valparaiso OSM crawler and persist results."""

    run: Optional[CrawlRun] = db.get(CrawlRun, run_id)
    if run is None:
        raise RuntimeError(f"Run not found in DB: {run_id}")

    run_dir = _run_dir_for(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "run.log"

    cmd = _script_command_for_valpo(request, run_dir)
    params_json = request.model_dump_json()

    run.params_json = params_json
    run.reference_address = request.reference_address
    run.city_query = request.city_query
    run.log_path = str(log_path)
    run.started_at = datetime.utcnow()
    run.status = "running"
    db.add(run)
    db.commit()

    try:
        with log_path.open("w", encoding="utf-8") as f:
            completed = subprocess.run(
                cmd,
                cwd=REPO_ROOT,
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
            exit_code = completed.returncode

        if exit_code != 0:
            raise RuntimeError(f"Crawler exited with code {exit_code}")

        businesses = _load_findings(run_dir)

        findings: List[CrawlFinding] = []
        for row in businesses:
            findings.append(
                CrawlFinding(
                    run_id=run_id,
                    name=str(row.get("name", "")),
                    business_type=str(row.get("business_type", "")),
                    phone=str(row.get("phone", "N/A")),
                    website=str(row.get("website", "N/A")),
                    email=str(row.get("email", "N/A")),
                    opening_hours=str(row.get("opening_hours", "N/A")),
                    location=str(row.get("location", "")),
                    latitude=float(row.get("latitude", 0.0)),
                    longitude=float(row.get("longitude", 0.0)),
                    distance_miles=float(row.get("distance_miles", 0.0)),
                    quality_score=int(row.get("quality_score", 0)),
                    source=row.get("source"),
                )
            )

        db.query(CrawlFinding).filter(CrawlFinding.run_id == run_id).delete()
        db.add_all(findings)

        run.findings_count = len(findings)
        run.status = "completed"
        run.error_message = None
        run.completed_at = datetime.utcnow()
        db.commit()
    except (RuntimeError, OSError, json.JSONDecodeError, ValueError) as exc:
        run.status = "failed"
        run.error_message = f"{type(exc).__name__}: {exc}"
        run.completed_at = datetime.utcnow()
        logger.error("Run failed: %s", exc, exc_info=True)
        db.commit()
