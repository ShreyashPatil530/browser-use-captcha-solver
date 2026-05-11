"""
Central configuration for the CAPTCHA Solver Agent.
Edit CAPTCHA_SITES to add/remove targets. All LLM/path settings are env-driven.
"""
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Target CAPTCHA demo/test sites
# ---------------------------------------------------------------------------
CAPTCHA_SITES: list[dict] = [
    {
        "name": "Google_reCAPTCHA_v2",
        "url": "https://www.google.com/recaptcha/api2/demo",
        "type": "checkbox",
        "description": "Google reCAPTCHA v2 — I am not a robot checkbox",
    },
]

# ---------------------------------------------------------------------------
# Agent behaviour
# ---------------------------------------------------------------------------
MAX_AGENT_STEPS: int = 50       # image challenges need many steps (navigate+click+9 images+verify x3 rounds)
MAX_RETRIES: int = 1            # retries per site on hard error only
WAIT_BETWEEN_ACTIONS: float = 1.5   # seconds between agent actions
PAGE_LOAD_WAIT: float = 3.0     # seconds to wait for page load
NETWORK_IDLE_WAIT: float = 5.0  # seconds to wait for network idle

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
VIDEOS_DIR = BASE_DIR / "videos"
LOGS_DIR = BASE_DIR / "logs"
RESULTS_FILE = OUTPUT_DIR / "results.json"

# ---------------------------------------------------------------------------
# LLM settings  (all read from .env)
# ---------------------------------------------------------------------------
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openrouter").lower()
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free")

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------
CAPTURE_SCREENSHOTS: bool = os.getenv("CAPTURE_SCREENSHOTS", "true").lower() == "true"
HEADLESS: bool = os.getenv("HEADLESS", "false").lower() == "true"
