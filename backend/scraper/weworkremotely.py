"""WeWorkRemotely RSS scraper."""
import logging
import feedparser
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List, Optional
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)

CATEGORY_FEEDS = {
    "engineering": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "design": "https://weworkremotely.com/categories/remote-design-jobs.rss",
    "product": "https://weworkremotely.com/categories/remote-product-jobs.rss",
    "marketing": "https://weworkremotely.com/categories/remote-marketing-jobs.rss",
    "sales": "https://weworkremotely.com/categories/remote-sales-jobs.rss",
    "all": "https://weworkremotely.com/remote-jobs.rss",
}


class WeWorkRemotelyScraper(BaseScraper):

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

        html = await self._fetch(CATEGORY_FEEDS["all"])
        if not html:
            return []

        feed = feedparser.parse(html)
        for entry in feed.entries:
            try:
                posted_at = None
                if hasattr(entry, "published"):
                    try:
                        posted_at = parsedate_to_datetime(entry.published).replace(tzinfo=None)
                    except Exception:
                        posted_at = self._parse_posted_at(getattr(entry, "published", ""))

                if not self._is_recent(posted_at, max_age_hours):
                    continue

                # Check keyword match
                title = getattr(entry, "title", "")
                summary = getattr(entry, "summary", "")
                content = f"{title} {summary}".lower()
                if not any(kw.lower() in content for kw in keywords):
                    continue

                desc = BeautifulSoup(summary, "html.parser").get_text(separator="\n", strip=True)

                # ID from link
                link = getattr(entry, "link", "")
                job_id = link.split("/")[-1] or link[-16:]

                # Title format: "Company | Role"
                parts = title.split(": ", 1) if ": " in title else title.split(" — ", 1)
                company = parts[0].strip() if len(parts) > 1 else "Unknown"
                role = parts[1].strip() if len(parts) > 1 else title

                all_jobs.append({
                    "job_id": f"wwr_{job_id}",
                    "title": role,
                    "company": company,
                    "location": "Remote",
                    "remote": True,
                    "source": "weworkremotely",
                    "job_url": link,
                    "apply_url": link,
                    "description": desc,
                    "posted_at": posted_at,
                })
            except Exception as e:
                logger.debug(f"WWR parse error: {e}")

        logger.info(f"WeWorkRemotely: {len(all_jobs)} recent jobs matching keywords")
        return all_jobs
