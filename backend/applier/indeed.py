"""
Indeed job application automation.
Handles Indeed's native apply and external redirect tracking.
"""
import asyncio
import logging
import random
from typing import Tuple

from .base import BaseApplier
from .stealth_browser import StealthBrowser, human_type, human_click, poisson_delay, random_scroll
from .form_filler import FormFiller
from ..config import settings

logger = logging.getLogger(__name__)

INDEED_LOGIN_URL = "https://secure.indeed.com/auth"
INDEED_HOME_URL = "https://www.indeed.com/"


class IndeedApplier(BaseApplier):

    async def apply(self, job: dict) -> Tuple[bool, str]:
        proxy = random.choice(settings.PROXY_LIST) if settings.PROXY_LIST else None

        async with StealthBrowser(session_name="indeed", headless=settings.HEADLESS, proxy=proxy) as browser:
            page = await browser.new_page()
            filler = FormFiller()

            try:
                # Navigate to job
                await page.goto(job["apply_url"] or job["job_url"], wait_until="domcontentloaded", timeout=30000)
                await poisson_delay(2.0)
                await random_scroll(page)

                current_url = page.url

                # Check if redirected to external site
                if "indeed.com" not in current_url:
                    return await self._handle_external(page, filler, job)

                # Check if login needed
                if "login" in current_url or "signin" in current_url:
                    logged_in = await self.login(page)
                    if not logged_in:
                        return False, "Indeed login failed"
                    await page.goto(job["apply_url"] or job["job_url"], wait_until="domcontentloaded", timeout=30000)
                    await poisson_delay(1.5)

                # Look for Apply Now button
                apply_btn = None
                for sel in [
                    "button[id*='applyButton']",
                    "a[id*='applyButton']",
                    "button:has-text('Apply now')",
                    "a:has-text('Apply now')",
                    "#apply-button-link",
                    ".jobsearch-ApplyButton",
                ]:
                    try:
                        apply_btn = await page.wait_for_selector(sel, timeout=5000)
                        if apply_btn and await apply_btn.is_visible():
                            break
                        apply_btn = None
                    except Exception:
                        pass

                if not apply_btn:
                    return False, "No apply button found on Indeed"

                await apply_btn.click()
                await poisson_delay(2.0)

                # Handle multi-page indeed apply
                return await self._handle_indeed_apply(page, filler, job)

            except Exception as e:
                logger.error(f"Indeed apply error: {e}", exc_info=True)
                return False, f"Error: {str(e)[:200]}"
            finally:
                await page.close()

    async def login(self, page) -> bool:
        if not settings.INDEED_EMAIL or not settings.INDEED_PASSWORD:
            return False

        try:
            await page.goto(INDEED_LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
            await poisson_delay(1.5)

            await human_type(page, "input[type='email']", settings.INDEED_EMAIL)
            await poisson_delay(0.5)

            continue_btn = await page.query_selector("button:has-text('Continue')")
            if continue_btn:
                await continue_btn.click()
                await poisson_delay(1.5)

            await human_type(page, "input[type='password']", settings.INDEED_PASSWORD)
            await poisson_delay(0.5)

            signin_btn = await page.query_selector("button:has-text('Sign in')")
            if signin_btn:
                await signin_btn.click()

            await page.wait_for_load_state("networkidle", timeout=15000)
            await poisson_delay(2.0)
            return "indeed.com" in page.url

        except Exception as e:
            logger.error(f"Indeed login error: {e}")
            return False

    async def _handle_indeed_apply(self, page, filler: FormFiller, job: dict) -> Tuple[bool, str]:
        max_steps = 8
        for step in range(max_steps):
            await poisson_delay(1.0)
            await filler.fill_form(page, job)

            if job.get("resume_path"):
                try:
                    await filler.upload_resume(page, job["resume_path"])
                except Exception:
                    pass

            await poisson_delay(0.8)

            # Submit
            submit_btn = None
            for sel in ["button:has-text('Submit your application')", "button:has-text('Submit')", "#form-action-submit"]:
                try:
                    submit_btn = await page.query_selector(sel)
                    if submit_btn and await submit_btn.is_visible():
                        break
                    submit_btn = None
                except Exception:
                    pass

            if submit_btn:
                await submit_btn.click()
                await poisson_delay(2.5)

                # Check success
                try:
                    await page.wait_for_selector(
                        "h1:has-text('application'), h2:has-text('submitted'), .ia-BasePage-bodyHeader",
                        timeout=8000
                    )
                    return True, "Applied"
                except Exception:
                    if "confirmation" in page.url or "success" in page.url:
                        return True, "Applied (URL confirmation)"
                    return False, "Submitted but no confirmation"

            # Next step
            next_btn = None
            for sel in ["button:has-text('Continue')", "button:has-text('Next')", "button[type='submit']:not(:has-text('Submit'))"]:
                try:
                    next_btn = await page.query_selector(sel)
                    if next_btn and await next_btn.is_visible():
                        break
                    next_btn = None
                except Exception:
                    pass

            if next_btn:
                await next_btn.click()
                continue

            return False, f"No actionable button at step {step + 1}"

        return False, "Max steps exceeded"

    async def _handle_external(self, page, filler: FormFiller, job: dict) -> Tuple[bool, str]:
        """Handle external company application sites."""
        await poisson_delay(2.0)
        await filler.fill_form(page, job)

        if job.get("resume_path"):
            await filler.upload_resume(page, job["resume_path"])

        # Try to submit
        submit_btn = None
        for sel in ["button[type='submit']", "input[type='submit']", "button:has-text('Submit')", "button:has-text('Apply')"]:
            try:
                submit_btn = await page.query_selector(sel)
                if submit_btn and await submit_btn.is_visible():
                    break
                submit_btn = None
            except Exception:
                pass

        if submit_btn:
            await submit_btn.click()
            await poisson_delay(2.0)
            return True, "Applied (external site)"

        return False, "External site — could not find submit button"
