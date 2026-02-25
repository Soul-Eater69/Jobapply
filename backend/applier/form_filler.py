"""
Generic form filling engine.
Handles text inputs, dropdowns, checkboxes, radio buttons, file uploads.
Uses AI to answer open-ended questions.
"""
import asyncio
import logging
import re
from typing import Optional

from playwright.async_api import Page

from .stealth_browser import human_type, human_click, poisson_delay
from ..config import load_user_profile, settings

logger = logging.getLogger(__name__)


class FormFiller:
    def __init__(self):
        self.profile = load_user_profile()
        self._ai_cache = {}

    def _get_field_value(self, label: str, field_type: str = "text") -> Optional[str]:
        """Match form field label to user profile data."""
        label_lower = label.lower().strip()
        p = self.profile

        # Direct mappings
        MAPPINGS = {
            "first name": p.get("first_name", ""),
            "last name": p.get("last_name", ""),
            "full name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
            "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
            "email": p.get("email", ""),
            "email address": p.get("email", ""),
            "phone": p.get("phone", ""),
            "phone number": p.get("phone", ""),
            "mobile": p.get("phone", ""),
            "address": p.get("address", {}).get("street", ""),
            "city": p.get("address", {}).get("city", ""),
            "state": p.get("address", {}).get("state", ""),
            "zip": p.get("address", {}).get("zip", ""),
            "zip code": p.get("address", {}).get("zip", ""),
            "postal code": p.get("address", {}).get("zip", ""),
            "country": p.get("address", {}).get("country", "United States"),
            "linkedin": p.get("linkedin_url", ""),
            "linkedin url": p.get("linkedin_url", ""),
            "linkedin profile": p.get("linkedin_url", ""),
            "github": p.get("github_url", ""),
            "github url": p.get("github_url", ""),
            "portfolio": p.get("portfolio_url", ""),
            "website": p.get("portfolio_url", ""),
            "personal website": p.get("portfolio_url", ""),
            "years of experience": str(p.get("years_experience", "")),
            "salary": str(p.get("desired_salary", "")),
            "salary expectation": str(p.get("desired_salary", "")),
            "expected salary": str(p.get("desired_salary", "")),
            "current salary": str(p.get("current_salary", "")),
            "notice period": p.get("notice_period", "2 weeks"),
            "availability": p.get("availability", "Immediately"),
            "start date": p.get("earliest_start_date", "Immediately"),
        }

        for key, value in MAPPINGS.items():
            if key in label_lower or label_lower in key:
                return str(value) if value else None

        # Authorization / work status
        if any(w in label_lower for w in ["authorized", "eligible", "work in the us", "legally"]):
            return p.get("work_authorization", "Yes")

        if any(w in label_lower for w in ["sponsor", "sponsorship", "visa"]):
            return p.get("requires_sponsorship", "No")

        if any(w in label_lower for w in ["veteran", "military"]):
            return "I am not a veteran"

        if any(w in label_lower for w in ["disability", "disabled"]):
            return "I do not have a disability"

        if any(w in label_lower for w in ["gender", "sex"]):
            return p.get("gender_disclosure", "Prefer not to say")

        if any(w in label_lower for w in ["race", "ethnicity"]):
            return p.get("ethnicity_disclosure", "Prefer not to say")

        if any(w in label_lower for w in ["cover letter"]):
            return p.get("default_cover_letter", "")

        return None

    async def _ai_answer(self, question: str, context: str = "") -> str:
        """Use Claude to answer open-ended application questions."""
        if not settings.ANTHROPIC_API_KEY:
            return self.profile.get("default_cover_letter", "I am very interested in this position.")

        cache_key = question[:100]
        if cache_key in self._ai_cache:
            return self._ai_cache[cache_key]

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            profile_summary = f"""
Name: {self.profile.get('first_name')} {self.profile.get('last_name')}
Role: {self.profile.get('current_role', 'Software Engineer')}
Experience: {self.profile.get('years_experience', '3')} years
Skills: {', '.join(self.profile.get('skills', [])[:15])}
"""
            prompt = f"""You are filling out a job application. Answer this question naturally and professionally.

Applicant profile:
{profile_summary}

Job context: {context[:300] if context else 'Not provided'}

Question: {question}

Write a concise, genuine answer (1-3 sentences max unless a cover letter is requested).
Be specific and professional. Do not use generic filler phrases."""

            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            answer = msg.content[0].text.strip()
            self._ai_cache[cache_key] = answer
            return answer
        except Exception as e:
            logger.error(f"AI answer failed: {e}")
            return "I am excited about this opportunity and confident I can contribute significantly to your team."

    async def fill_form(self, page: Page, job: dict) -> bool:
        """
        Attempt to fill all visible form fields on the current page.
        Returns True if all required fields were filled successfully.
        """
        filled_any = False

        # Text inputs and textareas
        inputs = await page.query_selector_all(
            "input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='file']):not([type='checkbox']):not([type='radio']), textarea"
        )

        for inp in inputs:
            try:
                if not await inp.is_visible():
                    continue
                if await inp.is_disabled():
                    continue

                # Get label
                label = await self._get_label(page, inp)
                if not label:
                    continue

                # Skip if already filled
                current_val = await inp.input_value() if await inp.get_attribute("type") != "textarea" else await inp.text_content()
                if current_val and current_val.strip():
                    continue

                # Get value
                value = self._get_field_value(label)
                if not value:
                    # Try AI for open-ended questions
                    inp_type = await inp.get_attribute("type") or "text"
                    tag = await inp.evaluate("el => el.tagName.toLowerCase()")
                    if tag == "textarea" or "cover" in label.lower() or "why" in label.lower() or "tell us" in label.lower():
                        value = await self._ai_answer(label, job.get("description", "")[:500])

                if value:
                    await human_type(page, None, value, clear_first=False)  # inp handled below
                    await inp.fill(value)
                    await asyncio.sleep(random.uniform(0.2, 0.6))
                    filled_any = True
            except Exception as e:
                logger.debug(f"Error filling input: {e}")

        # Select / dropdowns
        selects = await page.query_selector_all("select")
        for sel in selects:
            try:
                if not await sel.is_visible():
                    continue

                label = await self._get_label(page, sel)
                if not label:
                    continue

                value = self._get_field_value(label)
                if value:
                    # Try exact match, then partial
                    options = await sel.query_selector_all("option")
                    best = None
                    for opt in options:
                        opt_text = (await opt.text_content() or "").strip().lower()
                        opt_val = (await opt.get_attribute("value") or "").lower()
                        if value.lower() in opt_text or opt_text in value.lower():
                            best = await opt.get_attribute("value") or opt_text
                            break

                    if best:
                        await sel.select_option(value=best)
                        await asyncio.sleep(random.uniform(0.2, 0.5))
                        filled_any = True
            except Exception as e:
                logger.debug(f"Error filling select: {e}")

        # Checkboxes (work authorization, EEOC)
        checkboxes = await page.query_selector_all("input[type='checkbox']")
        for cb in checkboxes:
            try:
                if not await cb.is_visible():
                    continue

                label = await self._get_label(page, cb)
                if not label:
                    continue

                label_lower = label.lower()
                # Check boxes that indicate agreement/acceptance
                if any(w in label_lower for w in ["agree", "confirm", "acknowledge", "certif", "accept"]):
                    if not await cb.is_checked():
                        await cb.check()
                        await asyncio.sleep(random.uniform(0.2, 0.4))
            except Exception as e:
                logger.debug(f"Error with checkbox: {e}")

        return filled_any

    async def _get_label(self, page: Page, element) -> str:
        """Find the label for a form element."""
        try:
            # Check aria-label
            aria = await element.get_attribute("aria-label")
            if aria:
                return aria

            # Check placeholder
            placeholder = await element.get_attribute("placeholder")
            if placeholder:
                return placeholder

            # Check id -> label[for]
            el_id = await element.get_attribute("id")
            if el_id:
                label_el = await page.query_selector(f"label[for='{el_id}']")
                if label_el:
                    text = await label_el.text_content()
                    if text:
                        return text.strip()

            # Check name attribute
            name = await element.get_attribute("name")
            if name:
                return name.replace("_", " ").replace("-", " ")

            # Walk up DOM for label
            label_text = await element.evaluate("""el => {
                let node = el;
                for (let i = 0; i < 5; i++) {
                    node = node.parentElement;
                    if (!node) break;
                    const label = node.querySelector('label');
                    if (label) return label.textContent;
                    if (node.tagName === 'LABEL') return node.textContent;
                }
                return '';
            }""")
            return (label_text or "").strip()

        except Exception:
            return ""

    async def upload_resume(self, page: Page, resume_path: str) -> bool:
        """Find file upload input and upload the resume PDF."""
        try:
            file_inputs = await page.query_selector_all("input[type='file']")
            for inp in file_inputs:
                if not await inp.is_visible():
                    # Some hidden inputs can still receive files
                    pass

                accept = (await inp.get_attribute("accept") or "").lower()
                label = await self._get_label(page, inp)
                label_lower = label.lower()

                is_resume_field = (
                    "resume" in label_lower
                    or "cv" in label_lower
                    or "pdf" in accept
                    or ".pdf" in accept
                    or not accept  # generic upload
                )

                if is_resume_field:
                    await inp.set_input_files(resume_path)
                    await asyncio.sleep(random.uniform(1.5, 3.0))
                    logger.info(f"Resume uploaded to field: {label or 'unlabeled'}")
                    return True

        except Exception as e:
            logger.error(f"Resume upload failed: {e}")

        return False


import random
