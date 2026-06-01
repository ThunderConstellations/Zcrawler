from __future__ import annotations
# Run and persist crawls for Zcrawler webapp.

import json
import subprocess
import sys
import os
import shlex
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

import httpx
from webapp.app.logging_setup import setup_logging
from webapp.app.models import CrawlFinding, CrawlRun, CrawlerDefinition
from webapp.app.schemas import CreateRunRequest
from webapp.app.enrichment import extract_basic_info_from_url, generate_ai_summary

logger = setup_logging()

REPO_ROOT = Path(__file__).resolve().parents[2]
STORAGE_DIR = REPO_ROOT / "webapp" / "storage"


def _run_dir_for(run_id: str) -> Path:
    return STORAGE_DIR / "runs" / run_id


def _script_command_for_osm(request: CreateRunRequest, run_dir: Path, config: Dict[str, Any], limit: int = None) -> List[str]:
    script_path = REPO_ROOT / "scripts" / "osm_business_crawler.py"
    reference_address = config.get("reference_address", request.reference_address)
    city_query = config.get("city_query", request.city_query)
    categories = config.get("categories")
    radius_mi = config.get("radius_mi")
    limit = limit or config.get("limit")

    cmd = [sys.executable, str(script_path), "--reference-address", reference_address, "--city-query", city_query, "--output-dir", str(run_dir), "--max-reverse-geocode-lookups", str(request.max_reverse_geocode_lookups)]
    if not request.enable_reverse_geocode: cmd.append("--no-reverse-geocode")
    if categories: cmd.extend(["--categories", categories])
    if radius_mi: cmd.extend(["--radius-mi", str(radius_mi)])
    if limit: cmd.extend(["--limit", str(limit)])
    return cmd


def _script_command_for_directory(run_dir: Path, config: Dict[str, Any], ai_prompt: str = None, limit: int = None) -> List[str]:
    script_path = REPO_ROOT / "scripts" / "directory_scraper.py"
    url = config.get("url", "http://example.com")
    cmd = [sys.executable, str(script_path), "--url", url, "--output-dir", str(run_dir)]
    if ai_prompt:
        cmd.extend(["--ai-prompt", ai_prompt])
    if limit:
        cmd.extend(["--limit", str(limit)])
    return cmd

def _script_command_for_form_filler(url: str, profile_path: Path) -> List[str]:
    script_path = REPO_ROOT / "scripts" / "form_filler.py"
    return [sys.executable, str(script_path), "--url", url, "--profile-json", str(profile_path)]


def _load_findings(output_dir: Path) -> List[Dict[str, Any]]:
    output_json = output_dir / "businesses.json"
    if not output_json.exists():
        logger.warning("Output JSON not found at %s", output_json)
        return []
    try:
        payload = json.loads(output_json.read_text(encoding="utf-8"))
        return payload.get("businesses", [])
    except Exception as e:
        logger.error("Failed to load findings from %s: %s", output_json, e)
        return []


def execute_run(run_id: str, request: CreateRunRequest, db: Session) -> None:
    """Execute crawler and persist results."""
    run: Optional[CrawlRun] = db.get(CrawlRun, run_id)
    if run is None: raise RuntimeError(f"Run not found in DB: {run_id}")

    run_dir = _run_dir_for(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "run.log"

    config = {}
    ai_prompt = None
    if run.definition_id:
        definition = db.get(CrawlerDefinition, run.definition_id)
        if definition:
            ai_prompt = definition.ai_prompt
            if definition.config_json:
                try: config = json.loads(definition.config_json)
                except Exception: pass

    run.log_path = str(log_path)
    run.started_at = datetime.utcnow()
    run.status = "running"
    db.commit()

    try:
        findings: List[CrawlFinding] = []

        if run.template_key == "modular_workflow":
            steps = config.get("steps", [])
            with log_path.open("a", encoding="utf-8") as f:
                for idx, step in enumerate(steps):
                    f.write(f"\n--- Executing Step {idx+1}: {step.get('type')} ---\n")
                    f.flush()

                    stype = step.get("type")
                    sdesc = step.get("desc", "")

                    if stype == "search":
                        # Assume OSM search for now
                        osm_config = config.copy()
                        if sdesc and ":" in sdesc: # Simple parser for "categories:cafe"
                            k, v = sdesc.split(":", 1)
                            if k.strip() == "categories": osm_config["categories"] = v.strip()

                        cmd = _script_command_for_osm(request, run_dir, osm_config)
                        subprocess.run(cmd, cwd=REPO_ROOT, stdout=f, stderr=subprocess.STDOUT, check=False)
                        new_rows = _load_findings(run_dir)
                        for row in new_rows:
                            findings.append(CrawlFinding(
                                run_id=run_id, name=str(row.get("name", "")), business_type=str(row.get("business_type", "")),
                                phone=str(row.get("phone", "N/A")), website=str(row.get("website", "N/A")), email=str(row.get("email", "N/A")),
                                opening_hours=str(row.get("opening_hours", "N/A")), location=str(row.get("location", "")),
                                latitude=float(row.get("latitude", 0.0)), longitude=float(row.get("longitude", 0.0)),
                                distance_miles=float(row.get("distance_miles", 0.0)), quality_score=int(row.get("quality_score", 0)),
                                source="OSM"
                            ))

                    elif stype == "scrape":
                        # If we have findings, scrape their websites. Otherwise scrape a specific URL if provided in desc.
                        if not findings and "http" in sdesc:
                             f.write(f"Scraping single URL from description: {sdesc}\n")
                             f.flush()
                             scrape_dir = run_dir / f"scrape_{idx}_init"
                             cmd = _script_command_for_directory(scrape_dir, {"url": sdesc.strip()}, ai_prompt=ai_prompt, limit=5)
                             subprocess.run(cmd, cwd=REPO_ROOT, stdout=f, stderr=subprocess.STDOUT, check=False)
                             new_rows = _load_findings(scrape_dir)
                             for row in new_rows:
                                 findings.append(CrawlFinding(
                                     run_id=run_id, name=str(row.get("name", "")), business_type=str(row.get("business_type", "")),
                                     phone=str(row.get("phone", "N/A")), website=str(row.get("website", "N/A")), email=str(row.get("email", "N/A")),
                                     opening_hours=str(row.get("opening_hours", "N/A")), location=str(row.get("location", "")),
                                     source="Scraper"
                                 ))
                        else:
                            for b in findings[:3]: # Limit to 3 for safety in modular
                                 if not b.website or b.website == "N/A": continue
                                 f.write(f"Scraping {b.website} to enrich {b.name}...\n")
                                 f.flush()
                                 scrape_dir = run_dir / f"scrape_{idx}_{b.name.replace(' ', '_')}"
                                 cmd = _script_command_for_directory(scrape_dir, {"url": b.website}, ai_prompt=ai_prompt, limit=1)
                                 subprocess.run(cmd, cwd=REPO_ROOT, stdout=f, stderr=subprocess.STDOUT, check=False)
                                 details = _load_findings(scrape_dir)
                                 if details:
                                     # Merge details back to existing finding
                                     d = details[0]
                                     if not b.phone or b.phone == "N/A": b.phone = d.get("phone", "N/A")
                                     if not b.email or b.email == "N/A": b.email = d.get("email", "N/A")

                    elif stype == "enrich":
                        f.write(f"Enriching {len(findings)} findings...\n")
                        f.flush()
                        for b in findings[:5]:
                            if b.website and b.website != "N/A":
                                en = extract_basic_info_from_url(b.website)
                                b.description, b.social_links = en.get("description"), en.get("social_links")
                                b.ai_summary = generate_ai_summary(b.name, b.business_type, b.description or "")

                    elif stype == "form":
                        # Form automation step
                        profile_path = REPO_ROOT / "webapp" / "app" / "data" / "default_profile.json"
                        if not profile_path.exists():
                            profile_path.write_text(json.dumps({
                                "full_name": "John Doe", "email": "john@example.com", "phone": "555-0100",
                                "resume_text": "Experienced software engineer with a focus on Python and AI."
                            }))

                        target_url = sdesc if "http" in sdesc else "https://example.com/apply"
                        f.write(f"Attempting to fill form at {target_url}...\n")
                        f.flush()
                        cmd = _script_command_for_form_filler(target_url, profile_path)
                        subprocess.run(cmd, cwd=REPO_ROOT, stdout=f, stderr=subprocess.STDOUT, check=False)

                    elif stype == "vision_scrape":
                        f.write(f"Executing vision-based scrape for {sdesc}...\n")
                        f.flush()
                        # Capture screenshot and send to vision LLM
                        # For the demo, we'll log the intention
                        f.write("Vision Scraping Step: Element identification via Multimodal LLM initialized.\n")

                    elif stype == "export_airtable":
                        f.write(f"Exporting {len(findings)} findings to Airtable...\n")
                        f.flush()
                        from webapp.app.enrichment import get_api_key
                        airtable_key = get_api_key() # In a real app, use a specific key for Airtable
                        # Simplified implementation: Log the attempt
                        f.write("Airtable Export Initialized. (Simulated integration using System Settings)\n")

                    elif stype == "export_google":
                        f.write(f"Exporting {len(findings)} findings to Google Sheets...\n")
                        f.flush()
                        f.write("Google Sheets Export Initialized. (Simulated integration)\n")

        else:
            # Single template logic
            if run.template_key in ["osm_business_crawler"]:
                cmd = _script_command_for_osm(request, run_dir, config)
            elif run.template_key == "directory_scraper":
                cmd = _script_command_for_directory(run_dir, config, ai_prompt=ai_prompt)
            else:
                raise RuntimeError(f"Unsupported template_key: {run.template_key}")

            with log_path.open("w", encoding="utf-8") as f:
                completed = subprocess.run(cmd, cwd=REPO_ROOT, stdout=f, stderr=subprocess.STDOUT, text=True, check=False)
                exit_code = completed.returncode
            if exit_code != 0: raise RuntimeError(f"Crawler exited with code {exit_code}")

            businesses = _load_findings(run_dir)
            for row in businesses:
                b = CrawlFinding(
                    run_id=run_id, name=str(row.get("name", "")), business_type=str(row.get("business_type", "")),
                    phone=str(row.get("phone", "N/A")), website=str(row.get("website", "N/A")), email=str(row.get("email", "N/A")),
                    opening_hours=str(row.get("opening_hours", "N/A")), location=str(row.get("location", "")),
                    latitude=float(row.get("latitude", 0.0)), longitude=float(row.get("longitude", 0.0)),
                    distance_miles=float(row.get("distance_miles", 0.0)), quality_score=int(row.get("quality_score", 0)),
                    source=row.get("source"),
                )
                # Auto-enrichment for single template
                if b.website and b.website != "N/A" and len(findings) < 5:
                    en = extract_basic_info_from_url(b.website)
                    b.description, b.social_links = en.get("description"), en.get("social_links")
                    b.ai_summary = generate_ai_summary(b.name, b.business_type, b.description or "")
                findings.append(b)

        # Persistence
        db.query(CrawlFinding).filter(CrawlFinding.run_id == run_id).delete()
        db.add_all(findings)
        run.findings_count, run.status, run.completed_at = len(findings), "completed", datetime.utcnow()
        db.commit()

        # Webhook Notification
        if run.webhook_url:
            try:
                logger.info("Sending completion webhook to %s", run.webhook_url)
                payload = {
                    "run_id": run.id,
                    "status": run.status,
                    "findings_count": run.findings_count,
                    "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                }
                httpx.post(run.webhook_url, json=payload, timeout=10)
            except Exception as e:
                logger.error("Failed to send webhook: %s", e)

    except Exception as exc:
        run.status, run.error_message, run.completed_at = "failed", f"{type(exc).__name__}: {exc}", datetime.utcnow()
        logger.error("Run failed: %s", exc, exc_info=True)
        db.commit()

def run_osm_business_crawler(run_id: str, request: CreateRunRequest, db: Session) -> None:
    """Legacy alias for execute_run."""
    execute_run(run_id, request, db)
