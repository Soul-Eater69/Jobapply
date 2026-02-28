"""
LinkedIn Easy Apply automation.
Handles multi-step Easy Apply forms with stealth browser.
"""
import asyncio
import logging
import random
from typing import Tuple

from .base import BaseApplier
from .stealth_browser import StealthBrowser, human_type_element, human_click, human_click_element, poisson_delay, random_scroll, detect_captcha
from .form_filler import FormFiller
from ..config import settings, load_user_profile

logger = logging.getLogger(__name__)

LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LINKEDIN_FEED_URL = "https://www.linkedin.com/feed/"


class LinkedInApplier(BaseApplier):

    async def apply(self, job: dict) -> Tuple[bool, str]:
        from ..config import settings
        headless = settings.HEADLESS

        proxy = random.choice(settings.PROXY_LIST) if settings.PROXY_LIST else None

        async with StealthBrowser(session_name="linkedin", headless=headless, proxy=proxy) as browser:
            page = await browser.new_page()
            filler = FormFiller()

            try:
                # Check if already logged in
                logged_in = await self._check_logged_in(page)
                if not logged_in:
                    logged_in = await self.login(page)
                    if not logged_in:
                        return False, "LinkedIn login failed"

                # Navigate to job
                await poisson_delay(2.0)
                await page.goto(job["job_url"], wait_until="domcontentloaded", timeout=30000)
                await poisson_delay(1.5)

                if await detect_captcha(page):
                    return False, "CAPTCHA detected on job page"

                await random_scroll(page)

                # Find Easy Apply button
                easy_apply_btn = None
                selectors = [
                    "button.jobs-apply-button",
                    "button[data-control-name='jobdetails_topcard_inapply']",
                    "button:has-text('Easy Apply')",
                    ".jobs-apply-button--top-card",
                ]
                for sel in selectors:
                    try:
                        easy_apply_btn = await page.wait_for_selector(sel, timeout=5000)
                        if easy_apply_btn:
                            break
                    except Exception:
                        pass

                if not easy_apply_btn:
                    return False, "No Easy Apply button found"

                # Check if already applied (LinkedIn shows "Withdraw" when already applied)
                already_applied = await page.query_selector("button:has-text('Withdraw'), .jobs-apply-button--withdrawn")
                if already_applied:
                    return False, "Already applied to this job"

                await easy_apply_btn.scroll_into_view_if_needed()
                await human_click_element(page, easy_apply_btn, browser=None)
                await poisson_delay(1.5)

                # Handle multi-step form
                success, reason = await self._handle_easy_apply_modal(page, filler, job)
                return success, reason

            except Exception as e:
                logger.error(f"LinkedIn apply error: {e}", exc_info=True)
                return False, f"Error: {str(e)[:200]}"
            finally:
                await page.close()

    async def login(self, page) -> bool:
        if not settings.LINKEDIN_EMAIL or not settings.LINKEDIN_PASSWORD:
            logger.warning("LinkedIn credentials not configured")
            return False

        try:
            await page.goto(LINKEDIN_LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
            await poisson_delay(1.5)

            username_el = await page.wait_for_selector("#username", timeout=10000)
            await human_type_element(username_el, settings.LINKEDIN_EMAIL)
            await poisson_delay(0.8)
            password_el = await page.wait_for_selector("#password", timeout=10000)
            await human_type_element(password_el, settings.LINKEDIN_PASSWORD)
            await poisson_delay(0.5)

            await human_click(page, "button[type='submit']")
            await page.wait_for_load_state("networkidle", timeout=15000)
            await poisson_delay(2.0)

            if await detect_captcha(page):
                logger.warning("CAPTCHA detected during LinkedIn login")
                return False

            # Verify login
            return await self._check_logged_in(page)
        except Exception as e:
            logger.error(f"LinkedIn login error: {e}")
            return False

    async def _check_logged_in(self, page) -> bool:
        try:
            await page.goto(LINKEDIN_FEED_URL, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)
            url = page.url
            return "feed" in url or "mynetwork" in url or "jobs" in url
        except Exception:
            return False

    async def _handle_easy_apply_modal(self, page, filler: FormFiller, job: dict) -> Tuple[bool, str]:
        """Walk through all steps of the Easy Apply modal."""
        max_steps = 10
        step = 0

        while step < max_steps:
            step += 1
            await poisson_delay(1.0)

            # Fill current step's form fields
            await filler.fill_form(page, job)

            # Upload resume if there's a file input
            if job.get("resume_path"):
                try:
                    await filler.upload_resume(page, job["resume_path"])
                except Exception:
                    pass

            await poisson_delay(0.8)

            # Check for Submit button
            submit_btn = None
            for sel in ["button[aria-label='Submit application']", "button:has-text('Submit application')", "button:has-text('Submit')"]:
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

                # Confirm success
                success_el = await page.query_selector("h3:has-text('application was sent')")
                if not success_el:
                    success_el = await page.query_selector("[data-test-modal-id='easy-apply-success-modal']")
                if not success_el:
                    # Check URL change or success message
                    try:
                        await page.wait_for_selector("text=application was sent", timeout=5000)
                        success_el = True
                    except Exception:
                        pass

                if success_el:
                    logger.info(f"Successfully applied to {job.get('title')} @ {job.get('company')}")
                    return True, "Applied"
                else:
                    return False, "Submit clicked but no success confirmation"

            # Check for Next/Continue button
            next_btn = None
            for sel in [
                "button[aria-label='Continue to next step']",
                "button:has-text('Next')",
                "button:has-text('Continue')",
                "button:has-text('Review')",
            ]:
                try:
                    next_btn = await page.query_selector(sel)
                    if next_btn and await next_btn.is_visible():
                        break
                    next_btn = None
                except Exception:
                    pass

            if next_btn:
                await next_btn.click()
                await poisson_delay(1.2)
                continue

            # Check for error messages
            error_el = await page.query_selector(".artdeco-inline-feedback--error, .jobs-easy-apply-form-element__error")
            if error_el:
                error_text = await error_el.text_content()
                return False, f"Form validation error: {(error_text or '').strip()[:200]}"

            # No actionable button found
            return False, f"Stuck at step {step} — no Next/Submit button found"

        return False, "Max form steps exceeded"
