"""
Greenhouse job board scraper.
Many companies (Stripe, Airbnb, Figma, etc.) post jobs on Greenhouse.
We can directly hit their public job APIs.
"""
import logging
from datetime import datetime
from typing import List, Optional
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)

# Well-known companies using Greenhouse (add more as needed)
GREENHOUSE_COMPANIES = [
    "stripe", "figma", "notion", "discord", "datadog", "plaid",
    "brex", "robinhood", "lyft", "reddit", "twitch", "coinbase",
    "cloudflare", "asana", "segment", "sendgrid", "okta", "zendesk",
]


class GreenhouseScraper(BaseScraper):
    BOARD_API = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs"

    async def search_jobs(
        self,
        keywords: List[str],
        locations: List[str],
        max_age_hours: int = 1,
        remote_only: bool = False,
        job_types: Optional[List[str]] = None,
        experience_levels: Optional[List[str]] = None,
        target_companies: Optional[List[str]] = None,
        **kwargs,
    ) -> List[dict]:
        companies = target_companies or GREENHOUSE_COMPANIES
        all_jobs = []

        for company in companies:
            jobs = await self._scrape_company(company, keywords, max_age_hours, remote_only)
            all_jobs.extend(jobs)

        seen = set()
        unique = []
        for j in all_jobs:
            if j["job_id"] not in seen:
                seen.add(j["job_id"])
                unique.append(j)
        return unique

    async def _scrape_company(
        self,
        company: str,
        keywords: List[str],
        max_age_hours: int,
        remote_only: bool,
    ) -> List[dict]:
        url = self.BOARD_API.format(company=company)
        data = await self._fetch_json(url, params={"content": "true"})
        if not data:
            return []

        jobs = []
        for item in data.get("jobs", []):
            try:
                title = item.get("title", "")
                # Keyword filter
                if not any(kw.lower() in title.lower() for kw in keywords):
                    continue

                # Location filter
                location = item.get("location", {}).get("name", "")
                if remote_only and "remote" not in location.lower():
                    continue

                updated = item.get("updated_at", "")
                posted_at = None
                if updated:
                    try:
                        posted_at = datetime.fromisoformat(updated.replace("Z", ""))
                    except Exception:
                        pass

                if not self._is_recent(posted_at, max_age_hours):
                    continue

                job_id = item.get("id")
                job_url = item.get("absolute_url", f"https://boards.greenhouse.io/{company}/jobs/{job_id}")

                # Parse description
                desc_html = item.get("content", "")
                description = BeautifulSoup(desc_html, "html.parser").get_text(separator="\n", strip=True) if desc_html else ""

                jobs.append({
                    "job_id": f"greenhouse_{job_id}",
                    "title": title,
                    "company": company.title(),
                    "location": location,
                    "remote": "remote" in location.lower(),
                    "source": "greenhouse",
                    "job_url": job_url,
                    "apply_url": job_url,
                    "description": description,
                    "posted_at": posted_at,
                })
            except Exception as e:
                logger.debug(f"Greenhouse parse error [{company}]: {e}")

        return jobs
