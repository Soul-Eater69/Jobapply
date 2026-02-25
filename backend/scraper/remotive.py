"""Remotive.com scraper — public JSON API, no auth needed."""
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from .base import BaseScraper

logger = logging.getLogger(__name__)


class RemotiveScraper(BaseScraper):
    API_URL = "https://remotive.com/api/remote-jobs"

    async def search_jobs(
        self,
        keywords: List[str],
        locations: List[str],
        max_age_hours: int = 1,
        remote_only: bool = False,
        job_types: Optional[List[str]] = None,
        experience_levels: Optional[List[str]] = None,
        **kwargs,
    ) -> List[dict]:
        all_jobs = []

        for keyword in keywords:
            jobs = await self._search(keyword, max_age_hours)
            all_jobs.extend(jobs)

        seen = set()
        unique = []
        for j in all_jobs:
            if j["job_id"] not in seen:
                seen.add(j["job_id"])
                unique.append(j)
        return unique

    async def _search(self, keyword: str, max_age_hours: int) -> List[dict]:
        data = await self._fetch_json(self.API_URL, params={"search": keyword, "limit": 50})
        if not data:
            return []

        jobs = []
        for item in data.get("jobs", []):
            try:
                job = self._parse(item, max_age_hours)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"Remotive parse error: {e}")

        logger.info(f"Remotive [{keyword}]: {len(jobs)} recent jobs")
        return jobs

    def _parse(self, item: dict, max_age_hours: int) -> Optional[dict]:
        posted_str = item.get("publication_date", "")
        posted_at = None
        if posted_str:
            try:
                posted_at = datetime.fromisoformat(posted_str.replace("Z", ""))
            except Exception:
                pass

        if not self._is_recent(posted_at, max_age_hours):
            return None

        from bs4 import BeautifulSoup
        desc_html = item.get("description", "")
        description = BeautifulSoup(desc_html, "html.parser").get_text(separator="\n", strip=True)

        tags = item.get("tags", [])
        salary = item.get("salary", "")

        return {
            "job_id": f"remotive_{item.get('id')}",
            "title": item.get("title", ""),
            "company": item.get("company_name", "Unknown"),
            "location": item.get("candidate_required_location", "Remote"),
            "remote": True,
            "source": "remotive",
            "job_url": item.get("url", ""),
            "apply_url": item.get("url", ""),
            "description": description,
            "salary": salary or None,
            "job_type": item.get("job_type"),
            "posted_at": posted_at,
        }
