"""
Utility functions: logging, JSON/CSV output, directory bootstrap.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from config import LOGS_DIR, OUTPUT_DIR, RESULTS_FILE, SCREENSHOTS_DIR, VIDEOS_DIR


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging() -> logging.Logger:
    LOGS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    log = logging.getLogger("captcha_solver")
    log.setLevel(logging.INFO)
    log.propagate = False

    if not log.handlers:
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        log.addHandler(ch)

        fh = logging.FileHandler(
            LOGS_DIR / f"captcha_{timestamp}.log", encoding="utf-8"
        )
        fh.setFormatter(fmt)
        log.addHandler(fh)

    return log


logger = _setup_logging()


# ---------------------------------------------------------------------------
# Directory bootstrap
# ---------------------------------------------------------------------------

def ensure_dirs() -> None:
    for d in (OUTPUT_DIR, SCREENSHOTS_DIR, VIDEOS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Results persistence
# ---------------------------------------------------------------------------

def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not JSON serializable: {type(obj)}")


def save_results(results: list[dict]) -> None:
    """Write all results to output/results.json and output/results.csv."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    if not results:
        logger.warning("save_results called with empty list — nothing written.")
        return

    # JSON
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=_json_default, ensure_ascii=False)
    logger.info(f"JSON -> {RESULTS_FILE}  ({len(results)} records)")

    # CSV
    csv_path = OUTPUT_DIR / "results.csv"
    rows = [
        {
            "site_name": r.get("site_name", ""),
            "type": r.get("type", ""),
            "status": r.get("status", ""),
            "steps_taken": r.get("steps_taken", 0),
            "elapsed_seconds": r.get("elapsed_seconds", 0),
            "agent_output": r.get("agent_output", ""),
            "screenshot_path": r.get("screenshot_path", ""),
            "video_path": r.get("video_path", ""),
            "timestamp": r.get("timestamp", ""),
            "url": r.get("url", ""),
        }
        for r in results
    ]
    columns = ["site_name", "type", "status", "steps_taken", "elapsed_seconds",
               "agent_output", "screenshot_path", "video_path", "timestamp", "url"]
    pd.DataFrame(rows, columns=columns).to_csv(csv_path, index=False, encoding="utf-8")
    logger.info(f"CSV  -> {csv_path}  ({len(rows)} rows)")


def append_result(result: dict, all_results: list[dict]) -> None:
    """Add result to list and immediately persist so partial runs are recoverable."""
    all_results.append(result)
    save_results(all_results)


# ---------------------------------------------------------------------------
# Console summary table
# ---------------------------------------------------------------------------

def print_summary(results: list[dict]) -> None:
    logger.info("")
    logger.info("=" * 72)
    logger.info(f"{'SITE':<30} {'TYPE':<12} {'STATUS':<10} {'STEPS':>5} {'TIME':>6}s")
    logger.info("-" * 72)
    for r in results:
        name = r.get("site_name", "")[:29]
        ctype = r.get("type", "")[:11]
        status = r.get("status", "")[:9]
        steps = r.get("steps_taken", 0)
        elapsed = r.get("elapsed_seconds", 0)
        logger.info(f"{name:<30} {ctype:<12} {status:<10} {steps:>5} {elapsed:>6.1f}")
    logger.info("=" * 72)

    success = sum(1 for r in results if r.get("status") == "success")
    partial = sum(1 for r in results if r.get("status") == "partial")
    failed  = sum(1 for r in results if r.get("status") in ("failed", "error", "unknown"))

    logger.info(f"TOTAL: {len(results)} sites | success={success} | partial={partial} | failed={failed}")
    logger.info("=" * 72)
    logger.info("")
