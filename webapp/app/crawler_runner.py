from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from webapp.app.db import SessionLocal
from webapp.app.enrichment import (
    extract_basic_info_from_url,
    generate_ai_summary,
    analyze_sentiment,
    clean_data_with_ai,
    evaluate_semantic_change,
    vision_extract_from_image,
    extract_salary_range
)
from webapp.app.models import CrawlFinding, CrawlRun, CrawlerDefinition, FindingHistory
from webapp.app.schemas import CreateRunRequest

REPO_ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger("zcrawler")


def get_rotated_proxy() -> Optional[str]:
    return os.getenv("PROXY_URL")


def get_stealth_profile(url: str) -> Dict[str, Any]:
    if "google" in url: return {"user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    if "linkedin" in url: return {"user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    return {"user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

def execute_run(run_id: str, request: CreateRunRequest, db: Session) -> None:
    run = db.get(CrawlRun, run_id)
    if not run: return
    try:
        run.status, run.started_at, run.progress, run.status_message = "running", datetime.utcnow(), 0, "INIT_CORE"
        db.commit()
        run_dir = Path(run.output_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = run_dir / "run.log"
        run.log_path = str(log_path)
        def_obj = db.get(CrawlerDefinition, run.definition_id) if run.definition_id else None
        config = json.loads(def_obj.config_json) if def_obj else {}
        if def_obj and not run.organization_id: run.organization_id = def_obj.organization_id
        findings: List[CrawlFinding] = []

        if run.template_key == "modular_workflow":
            steps = config.get("steps", [])
            with log_path.open("w", encoding="utf-8") as f:
                for idx, step in enumerate(steps):
                    stype, sdesc = step.get("type"), step.get("desc", "")
                    run.progress, run.status_message = int((idx / len(steps)) * 100), f"SYST_EXEC: {stype.upper()}"
                    db.commit()
                    if stype == "search":
                        osm_config = config.copy()
                        if ":" in sdesc:
                            k, v = sdesc.split(":", 1)
                            if k.strip() == "categories": osm_config["categories"] = v.strip()
                        subprocess.run(_script_command_for_osm(request, run_dir, osm_config), cwd=REPO_ROOT, stdout=f, stderr=subprocess.STDOUT)
                        for row in _load_findings(run_dir):
                            findings.append(CrawlFinding(run_id=run_id, name=str(row.get("name", "")), business_type=str(row.get("business_type", "Node")), phone=str(row.get("phone", "N/A")), website=str(row.get("website", "N/A")), email=str(row.get("email", "N/A")), location=str(row.get("location", "")), latitude=float(row.get("latitude", 0.0)), longitude=float(row.get("longitude", 0.0)), distance_miles=float(row.get("distance_miles", 0.0)), source="OSM"))

                    elif stype == "scrape":
                        for b in (findings if findings else [{"website": sdesc}])[:5]:
                             w = b.website if isinstance(b, CrawlFinding) else b["website"]
                             if not w or w == "N/A": continue
                             f.write(f"TRANS_ENTRY: {w}
")
                             # Apply Site-Specific Stealth Profile
                             profile = get_stealth_profile(w)
                             f.write(f"  -> Applying Stealth Profile: {profile['user_agent'][:50]}...
")

                             scrape_dir = run_dir / f"scrape_{idx}"
                             subprocess.run(_script_command_for_directory(scrape_dir, {"url": w}), cwd=REPO_ROOT, stdout=f, stderr=subprocess.STDOUT)

                             details = _load_findings(scrape_dir)
                             if details:
                                 d = details[0]
                                 if isinstance(b, CrawlFinding):
                                     b.phone, b.email = d.get("phone", b.phone), d.get("email", b.email)

                                     if "job" in b.business_type.lower():
                                         b.description = (b.description or "") + f"\n\nSalary: {extract_salary_range(d.get('raw_html', ''))}"
                                         # Referral Check
                                         profile_data = json.loads(p_path.read_text()) if p_path.exists() else {}
                                         from webapp.app.enrichment import find_referral_contacts
                                         refs = find_referral_contacts(d.get('raw_html', ''), profile_data.get('referral_contacts', []))
                                         if refs: b.description += f"\n\nPotential Referrals: {', '.join(refs)}"

                    elif stype == "enrich":
                        for b in findings[:10]:
                            if b.website and b.website != "N/A":
                                en = extract_basic_info_from_url(b.website)
                                b.description, b.social_links = en.get("description"), en.get("social_links")
                                b.ai_summary = generate_ai_summary(b.name, b.business_type, b.description or "")
                    elif stype == "sentiment_analysis":
                        for b in findings[:10]:
                            if b.description: b.ai_summary = (b.ai_summary or "") + f" | Sentiment: {analyze_sentiment(b.description)}"
                    elif stype == "data_cleaning":
                        for b in findings:
                            if b.phone: b.phone = b.phone.replace(" ", "").replace("-", "")
                    elif stype == "if_then":
                        cond, act = sdesc.split("then", 1) if "then" in sdesc else (sdesc, "")
                        f.write(f"LOGIC_EVAL: {cond}\n")
                    elif stype == "semantic_alert":
                        for b in findings[:3]:
                            msg = evaluate_semantic_change("PREV", str(b.__dict__), sdesc)
                            if msg: f.write(f"ALERT_TRIGGERED: {msg}\n")
                    elif stype == "vision_scrape":
                        f.write(f"VISION_SYNC: {sdesc}\n")
                    elif stype == "form":
                        p_name = config.get("profile_name", "default_profile")
                        p_path = REPO_ROOT / "webapp" / "app" / "data" / f"{p_name}.json"
                        target = sdesc if "http" in sdesc else findings[0].website if findings else "https://example.com"
                        subprocess.run(_script_command_for_form_filler(target, p_path), cwd=REPO_ROOT, stdout=f, stderr=subprocess.STDOUT)
        else:
            run.status_message = "MONO_ENGINE_ACTIVE"
            db.commit()
            cmd = _script_command_for_osm(request, run_dir, config) if run.template_key == "osm_business_crawler" else _script_command_for_directory(run_dir, config)
            with log_path.open("w", encoding="utf-8") as f: subprocess.run(cmd, cwd=REPO_ROOT, stdout=f, stderr=subprocess.STDOUT)
            for row in _load_findings(run_dir):
                findings.append(CrawlFinding(run_id=run_id, name=str(row.get("name", "")), business_type=str(row.get("business_type", "")), phone=str(row.get("phone", "N/A")), website=str(row.get("website", "N/A")), email=str(row.get("email", "N/A")), location=str(row.get("location", "")), latitude=float(row.get("latitude", 0.0)), longitude=float(row.get("longitude", 0.0)), distance_miles=float(row.get("distance_miles", 0.0)), source=row.get("source")))

        for new_f in findings:
            old_f = db.query(CrawlFinding).filter(CrawlFinding.name == new_f.name, CrawlFinding.location == new_f.location).first()
            if old_f:
                for field in ['phone', 'website']:
                    ov, nv = getattr(old_f, field), getattr(new_f, field)
                    if ov != nv: db.add(FindingHistory(finding_id=old_f.id, field_name=field, old_value=ov, new_value=nv))
        db.query(CrawlFinding).filter(CrawlFinding.run_id == run_id).delete()
        db.add_all(findings)
        run.findings_count, run.status, run.completed_at, run.progress, run.status_message = len(findings), "completed", datetime.utcnow(), 100, "MISSION_SUCCESS"
        db.commit()
    except Exception as exc:
        run.status, run.error_message, run.completed_at = "failed", str(exc), datetime.utcnow()
        try:
            from webapp.app.enrichment import analyze_error_with_ai
            log_tail = open(run.log_path).read()[-1000:] if os.path.exists(run.log_path) else ""
            run.ai_fix_suggestion = analyze_error_with_ai(log_tail, run.error_message)
        except: pass
        db.commit()

def _script_command_for_osm(request, run_dir, config):
    ref = config.get("anchor") or config.get("reference_address") or request.reference_address
    city = config.get("city_query", request.city_query)
    cmd = [sys.executable, "scripts/osm_business_crawler.py", "--reference-address", ref, "--city-query", city, "--output-dir", str(run_dir)]
    if config.get("categories"): cmd.extend(["--categories", config["categories"]])
    if config.get("radius_mi"): cmd.extend(["--radius-mi", str(config["radius_mi"])])
    if config.get("limit"): cmd.extend(["--limit", str(config["limit"])])
    return cmd

def _script_command_for_directory(run_dir, config):
    return [sys.executable, "scripts/directory_scraper.py", "--url", config.get("url", "http://example.com"), "--output-dir", str(run_dir)]

def _script_command_for_form_filler(url, profile_path):
    return [sys.executable, "scripts/form_filler.py", "--url", url, "--profile-json", str(profile_path)]

def _load_findings(run_dir):
    p = run_dir / "businesses.json"
    if not p.exists(): return []
    try: return json.loads(p.read_text()).get("businesses", [])
    except: return []

def run_osm_business_crawler(run_id: str, request: CreateRunRequest, db: Session) -> None:
    """Legacy alias for backward compatibility with scheduler."""
    execute_run(run_id, request, db)
