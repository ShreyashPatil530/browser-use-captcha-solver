"""
Core CAPTCHA solving agent using browser-use.

Each CaptchaAgent instance handles one site:
  1. Builds a type-specific task prompt
  2. Runs a browser-use Agent with use_vision=True
  3. Extracts output from done() call OR last action result
  4. Retries ONLY on hard errors (exceptions), not on failed/unknown
"""
import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from browser_use import Agent, BrowserProfile, BrowserSession

from config import (
    CAPTURE_SCREENSHOTS,
    HEADLESS,
    MAX_AGENT_STEPS,
    MAX_RETRIES,
    NETWORK_IDLE_WAIT,
    PAGE_LOAD_WAIT,
    SCREENSHOTS_DIR,
    VIDEOS_DIR,
    WAIT_BETWEEN_ACTIONS,
)
from utils import logger


class CaptchaAgent:
    """Handles one CAPTCHA site — builds prompt, runs agent, returns result dict."""

    def __init__(self, site: dict, llm: Any) -> None:
        self.site = site
        self.llm = llm

    # ------------------------------------------------------------------
    # Task prompts per CAPTCHA type
    # ------------------------------------------------------------------

    def _build_task_prompt(self) -> str:
        url = self.site["url"]
        ctype = self.site.get("type", "checkbox")
        name = self.site["name"]

        # Common rules appended to every prompt
        common_rules = """
CRITICAL RULES:
- You have up to 50 steps — use ALL of them if needed. Do NOT stop early.
- Do NOT call done() until you have either clearly succeeded OR clearly failed after trying everything.
- After clicking "Verify", wait 3-5 seconds then check if another round appeared.
- The CAPTCHA may be inside an iframe — click directly on the visible widget element.
- When done() is called, the EXACT text must start with SUCCESS or FAILED or PARTIAL.
"""

        if ctype == "checkbox":
            return f"""You are a human acting on a browser. Solve the human verification on this demo page.

URL: {url}

TASK: Click the "I am not a robot" checkbox and complete any image challenge that appears.

STEP-BY-STEP:
1. Go to {url} and wait for the page to fully load (3 seconds).
2. Get the full DOM content to find the reCAPTCHA widget.
3. Click the checkbox element inside the reCAPTCHA iframe (the "I am not a robot" checkbox).
   - The checkbox is inside an iframe with src containing "recaptcha"
   - Its element index in the DOM will be near elements labeled "recaptcha" or "rc-anchor"
4. Wait 4 seconds. Get the page content again to see what appeared.
5. IF an image challenge appeared (look for a table or grid of clickable images):
   a. Read the challenge instruction text (e.g. "Select all squares with traffic lights").
   b. Click ALL image tiles in the grid — there are 9 tiles (index them 1-9, click every one).
      Even if you cannot see the images, clicking all of them and verifying is acceptable.
   c. Look for a button labeled "VERIFY" or "Verify" and click it.
   d. Wait 3 seconds. Check if a new challenge appeared or if the checkbox now shows a checkmark.
   e. If new challenge appeared — repeat: click all 9 image tiles again, then click Verify.
   f. Repeat up to 3 rounds.
6. IF no image challenge appeared — look for a green checkmark on the checkbox (class "recaptcha-checkbox-checked" or similar).
7. Once a green checkmark is visible OR the form can be submitted:
   - Call done() with: "SUCCESS - checkbox verified and CAPTCHA solved"
8. If after 3 rounds the challenge keeps appearing:
   - Call done() with: "FAILED - could not solve CAPTCHA after multiple attempts"
{common_rules}"""

        if ctype == "image":
            return f"""You are a human acting on a browser. Solve the image CAPTCHA on this demo page.

URL: {url}

TASK: Solve the image selection challenge — identify and click the correct images, then verify.

STEP-BY-STEP:
1. Go to {url} and wait for all images to fully load (3 seconds).
2. READ the challenge instruction VERY CAREFULLY (e.g. "Select all images with motorcycles").
3. Look at EVERY image one by one using your vision:
   - Analyze what is ACTUALLY in each image
   - Compare with the instruction requirement
   - Be precise: motorcycle ≠ car, traffic light ≠ vehicle
4. Click ONLY images that CLEARLY match the instruction:
   - Wait 300ms between clicks
   - Do NOT click images that don't match
   - Clicking wrong images = challenge fails
5. After clicking all matching images, look for "Verify" or "Submit" button.
6. Click "Verify" or "Submit" button.
7. Wait 3 seconds and check what happened:
   - If green checkmark or "success" message → Call done("SUCCESS - image CAPTCHA solved")
   - If NEW challenge appeared with fresh images → Repeat from step 2 (max 3 attempts)
   - If same challenge still visible → Try different images or call done("PARTIAL - could not complete")
8. After max 3 rounds, MUST call done() with:
   - "SUCCESS - image CAPTCHA solved"
   - "FAILED - could not identify correct images"
   - "PARTIAL - completed but uncertain"
{common_rules}"""

        if ctype == "turnstile":
            return f"""You are a human acting on a browser. Complete the Cloudflare verification on this page.

URL: {url}

TASK: Click the Cloudflare Turnstile "Verify you are human" checkbox and wait for it to pass.

STEP-BY-STEP:
1. Go to {url} and wait for page to load (3 seconds).
2. Find the Cloudflare Turnstile widget — it shows "Verify you are human" with a checkbox.
3. Click directly on the checkbox square inside the Turnstile widget.
4. Wait 8 seconds for automatic verification (Cloudflare checks in the background).
5. Look using vision: is there now a green checkmark or tick on the widget?
   - YES → Call done() with: "SUCCESS - Turnstile verified automatically"
   - NO, a challenge appeared → complete it (image selection, slider, etc.)
   - NO, still spinning → wait 5 more seconds and check again.
6. If verification never completes after 20 seconds:
   - Call done() with: "FAILED - Turnstile did not complete verification"
{common_rules}"""

        if ctype == "text":
            return f"""You are a human acting on a browser. Solve the text CAPTCHA on this demo page.

URL: {url}

TASK: Read the distorted text in the CAPTCHA image and type it into the input field.

STEP-BY-STEP:
1. Go to {url} and wait for page to load (3 seconds).
2. Find the CAPTCHA image showing distorted letters/numbers.
3. Look at the image very carefully with your vision. Read each character.
   - Common confusions: 0 vs O, 1 vs l vs I, rn vs m
4. Click the text input field below or beside the CAPTCHA image.
5. Type the characters you read EXACTLY (case-sensitive if needed).
6. Click the "Submit" or "Check" or "Verify" button.
7. Wait 2 seconds. Check for success or error message.
   - If "wrong" or "incorrect": click refresh/reload CAPTCHA image, read new one, try again (max 2 retries).
8. Call done() with:
   - "SUCCESS - text CAPTCHA solved, entered: [what you typed]"
   - "FAILED - could not read or enter correct CAPTCHA text"
{common_rules}"""

        return f"""You are a human acting on a browser. Complete the human verification on this page.

URL: {url}

TASK: Find and complete any CAPTCHA or human verification challenge on the page.

1. Go to {url} and wait for page to load.
2. Identify the verification widget.
3. Complete it using your best judgment.
4. Call done() with:
   - "SUCCESS - verification complete"
   - "FAILED - [reason]"
{common_rules}"""

    # ------------------------------------------------------------------
    # Extract final output — done() text OR last meaningful action result
    # ------------------------------------------------------------------

    def _extract_output(self, agent_result) -> str:
        # 1st: try final_result() — this is the done() text
        try:
            text = agent_result.final_result() or ""
            if text and text.strip():
                return text.strip()
        except Exception:
            pass

        # 2nd: scan action_results for is_done=True entry
        try:
            for ar in agent_result.action_results():
                if getattr(ar, "is_done", False):
                    content = getattr(ar, "extracted_content", "") or ""
                    if content.strip():
                        return content.strip()
        except Exception:
            pass

        # 3rd: return the last non-empty action content as a hint
        try:
            all_ar = list(agent_result.action_results())
            for ar in reversed(all_ar):
                content = getattr(ar, "extracted_content", "") or ""
                if content.strip() and len(content.strip()) > 3:
                    return f"[no done() call] last action: {content.strip()[:200]}"
        except Exception:
            pass

        return ""

    # ------------------------------------------------------------------
    # Single attempt
    # ------------------------------------------------------------------

    async def _run_once(self) -> dict:
        session: BrowserSession | None = None
        video_dir = VIDEOS_DIR / self.site["name"]
        video_dir.mkdir(parents=True, exist_ok=True)

        result = {
            "site_name": self.site["name"],
            "url": self.site["url"],
            "type": self.site.get("type", "unknown"),
            "status": "error",
            "agent_output": "",
            "steps_taken": 0,
            "elapsed_seconds": 0.0,
            "screenshot_path": "",
            "video_path": "",
            "timestamp": datetime.now().isoformat(),
        }

        try:
            profile = BrowserProfile(
                headless=HEADLESS,
                disable_security=True,
                minimum_wait_page_load_time=PAGE_LOAD_WAIT,
                wait_for_network_idle_page_load_time=NETWORK_IDLE_WAIT,
                wait_between_actions=WAIT_BETWEEN_ACTIONS,
                record_video_dir=str(video_dir),
                record_video_size={"width": 1280, "height": 720},
            )
            session = BrowserSession(browser_profile=profile)

            agent = Agent(
                task=self._build_task_prompt(),
                llm=self.llm,
                browser_session=session,
                use_vision=True,   # Gemma 3 4B has vision - can see and analyze images
                max_actions_per_step=5,
            )

            t0 = time.monotonic()
            agent_result = await agent.run(max_steps=MAX_AGENT_STEPS)
            elapsed = time.monotonic() - t0

            final_output = self._extract_output(agent_result)

            steps = 0
            try:
                steps = len(list(agent_result.action_results()))
            except Exception:
                pass

            result["steps_taken"] = steps
            result["elapsed_seconds"] = round(elapsed, 1)

            # Check if steps exceeded limit - treat as timeout
            if steps > MAX_AGENT_STEPS:
                result["status"] = "timeout"
                result["agent_output"] = f"TIMEOUT - exceeded {MAX_AGENT_STEPS} steps"
            else:
                result["agent_output"] = final_output
                upper = final_output.upper()
                if "SUCCESS" in upper:
                    result["status"] = "success"
                elif "PARTIAL" in upper:
                    result["status"] = "partial"
                elif "FAILED" in upper:
                    result["status"] = "failed"
                else:
                    result["status"] = "unknown"

            if CAPTURE_SCREENSHOTS:
                shot_path = await _save_screenshot(self.site["name"], self.site["url"])
                result["screenshot_path"] = shot_path

        except Exception as exc:
            err_str = str(exc)
            result["agent_output"] = err_str
            if "429" in err_str or "rate limit" in err_str.lower():
                result["status"] = "rate_limited"
                logger.warning(f"[{self.site['name']}] Rate limited — try again after daily reset")
            else:
                result["status"] = "error"
                logger.error(f"[{self.site['name']}] Exception: {exc}")
        finally:
            if session is not None:
                try:
                    await session.kill()
                except Exception:
                    pass

            # browser-use saves .mp4; Playwright raw saves .webm — check both
            await asyncio.sleep(2.0)
            video_files = sorted(
                list(video_dir.glob("*.mp4")) + list(video_dir.glob("*.webm")),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            if video_files:
                latest = video_files[0]
                # Only rename UUID-named files; skip already-renamed ones
                if latest.stem.replace("-", "").isalnum() and len(latest.stem) > 20:
                    timestamp = datetime.now().strftime("%H%M%S")
                    final_video = video_dir / f"session_{timestamp}{latest.suffix}"
                    latest.rename(final_video)
                    result["video_path"] = str(final_video)
                    logger.info(f"Video saved  -> {final_video}")
                else:
                    result["video_path"] = str(latest)
                    logger.info(f"Video saved  -> {latest}")
            else:
                logger.warning(f"No video file found in {video_dir}")

        return result

    # ------------------------------------------------------------------
    # Public entry — only retry on hard errors (exceptions), not on
    # failed/partial/unknown (those mean the agent ran, just didn't succeed)
    # ------------------------------------------------------------------

    async def solve(self) -> dict:
        name = self.site["name"]
        last_result: dict = {}

        for attempt in range(MAX_RETRIES + 1):
            logger.info(f"[{name}] Attempt {attempt + 1}/{MAX_RETRIES + 1}")
            result = await self._run_once()
            last_result = result

            if result["status"] == "success":
                logger.info(f"[{name}] SUCCESS — {result['agent_output']}")
                return result

            # Only retry on hard "error", not rate_limited/failed/partial/unknown
            if result["status"] == "error" and attempt < MAX_RETRIES:
                logger.warning(f"[{name}] Hard error — retrying once...")
                continue

            if result["status"] == "rate_limited":
                logger.warning(f"[{name}] Rate limited — skipping retries, will need daily reset")
                break

            # For failed/partial/unknown: agent ran, accept result as-is
            logger.info(
                f"[{name}] Done — status={result['status']} | "
                f"output={result['agent_output'][:100]}"
            )
            break

        return last_result


# ------------------------------------------------------------------
# Screenshot helper (fresh Playwright session, independent of agent)
# ------------------------------------------------------------------

async def _save_screenshot(site_name: str, url: str) -> str:
    from playwright.async_api import async_playwright

    dest_dir = Path(SCREENSHOTS_DIR) / site_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H%M%S")
    dest = dest_dir / f"final_{timestamp}.png"

    try:
        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception:
                browser = await pw.chromium.launch(
                    headless=False,
                    args=["--headless=new", "--no-sandbox", "--disable-dev-shm-usage"],
                )
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                await page.screenshot(path=str(dest), full_page=False)
                logger.info(f"Screenshot -> {dest}")
                return str(dest)
            finally:
                await browser.close()
    except Exception as exc:
        logger.warning(f"Screenshot failed for {site_name}: {exc}")
        return ""
