from __future__ import annotations

import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


def _purge_old_logs(log_dir: Path, max_age_seconds: float) -> None:
    """Remove log files older than max_age_seconds."""

    now = time.time()
    for item in log_dir.glob("*.log"):
        try:
            if now - item.stat().st_mtime > max_age_seconds:
                item.unlink(missing_ok=True)
        except OSError:
            # Best-effort cleanup; never fail the app because of logs.
            continue


def setup_logging(log_dir: Optional[Path] = None) -> logging.Logger:
    """Configure rotating logs for the crawler webapp."""

    if log_dir is None:
        log_dir = Path("webapp/logs")

    log_dir.mkdir(parents=True, exist_ok=True)
    # Keep logs for ~7 days (best-effort).
    _purge_old_logs(log_dir, max_age_seconds=7 * 24 * 60 * 60)

    logger = logging.getLogger("zcrawler_webapp")
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if Uvicorn reloads.
    if logger.handlers:
        return logger

    log_path = log_dir / "zcrawler.log"
    err_path = log_dir / "zcrawler_error.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(formatter)

    err_handler = RotatingFileHandler(
        err_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.addHandler(err_handler)
    logger.addHandler(stream_handler)
    return logger
