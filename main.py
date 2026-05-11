"""
Day 9 — CAPTCHA Solver Agent
=============================
Uses browser-use + vision to automatically handle human verification
challenges on public demo/test pages.

Usage:
    python main.py

Environment variables (set in .env):
    LLM_PROVIDER         openrouter (default)
    OPENROUTER_API_KEY   your OpenRouter API key
    OPENROUTER_MODEL     google/gemma-3-4b-it:free  (free vision model)
    HEADLESS             false (set true to hide browser)
    CAPTURE_SCREENSHOTS  true
"""

import asyncio
import io
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Fix Windows console encoding — browser-use emits emoji in log output
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config import (
    CAPTCHA_SITES,
    LLM_PROVIDER,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OUTPUT_DIR,
)
from captcha_agent import CaptchaAgent
from utils import append_result, ensure_dirs, logger, print_summary


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

def build_llm():
    if LLM_PROVIDER != "openrouter":
        raise ValueError(
            f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'. Only 'openrouter' configured."
        )
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set. Add it to your .env file.")

    from browser_use import ChatOpenAI

    return ChatOpenAI(
        model=OPENROUTER_MODEL,
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        temperature=0.0,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    ensure_dirs()

    logger.info("")
    logger.info("╔══════════════════════════════════════════════════╗")
    logger.info("║        Day 9 — CAPTCHA Solver Agent              ║")
    logger.info("║   browser-use + Vision                           ║")
    logger.info("╚══════════════════════════════════════════════════╝")
    logger.info("")

    try:
        llm = build_llm()
        logger.info(f"LLM Provider : {LLM_PROVIDER}")
        logger.info(f"Model        : {OPENROUTER_MODEL}")
        logger.info(f"Sites queued : {len(CAPTCHA_SITES)}")
        logger.info("")
    except ValueError as exc:
        logger.error(str(exc))
        sys.exit(1)

    all_results: list[dict] = []

    for i, site in enumerate(CAPTCHA_SITES, 1):
        logger.info("")
        logger.info("─" * 60)
        logger.info(f"  [{i}/{len(CAPTCHA_SITES)}] {site['name']}")
        logger.info(f"  Type   : {site['type']}")
        logger.info(f"  URL    : {site['url']}")
        logger.info(f"  Info   : {site['description']}")
        logger.info("─" * 60)

        agent = CaptchaAgent(site=site, llm=llm)
        result = await agent.solve()

        status_icon = {
            "success": "[OK]",
            "partial": "[~]",
            "failed":  "[X]",
            "error":   "[!]",
            "unknown": "[?]",
        }.get(result["status"], "[?]")

        logger.info(
            f"{status_icon} {site['name']} -> {result['status'].upper()} "
            f"({result['elapsed_seconds']}s, {result['steps_taken']} steps)"
        )
        logger.info(f"   Output: {result['agent_output'][:120]}")

        append_result(result, all_results)

    print_summary(all_results)

    logger.info(f"Results JSON : {OUTPUT_DIR / 'results.json'}")
    logger.info(f"Results CSV  : {OUTPUT_DIR / 'results.csv'}")
    logger.info(f"Screenshots  : day9-caption/screenshots/")
    logger.info(f"Videos       : day9-caption/videos/")
    logger.info("")


if __name__ == "__main__":
    asyncio.run(main())
