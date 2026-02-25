import logging
import re
import feedparser
from datetime import datetime
from typing import List, Optional
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime

from .base import BaseScraper

logger = logging.getLogger(__name__)


class IndeedScraper(BaseScraper):
    BASE_URL = "https://www.indeed.com"
    RSS_URL = "https://www.indeed.com/rss"
    SEARCH_URL = "https://www.indeed.com/jobs"

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
            for location in locations:
                # Use RSS for fresh jobs
                jobs = await self._search_rss(keyword, location, max_age_hours, remote_only, job_types)
                all_jobs.extend(jobs)

        seen = set()
        unique = []
        for j in all_jobs:
            if j["job_id"] not in seen:
                seen.add(j["job_id"])
                unique.append(j)
        return unique

    async def _search_rss(
        self,
        keyword: str,
        location: str,
        max_age_hours: int,
        remote_only: bool,
        job_types: Optional[List[str]],
    ) -> List[dict]:
        params = {
            "q": keyword,
            "l": "remote" if remote_only else location,
            "fromage": "1",  # Jobs from last 1 day (minimum)
            "sort": "date",
            "limit": "25",
        }

        if job_types:
            jt_map = {"full-time": "fulltime", "part-time": "parttime", "contract": "contract", "internship": "internship"}
            jt_list = [jt_map.get(jt.lower(), jt) for jt in job_types]
            params["jt"] = jt_list[0]  # Indeed only supports one at a time

        html = await self._fetch(self.RSS_URL, params=params)
        if not html:
            return []

        jobs = []
        try:
            feed = feedparser.parse(html)
            for entry in feed.entries:
                try:
                    # Parse date
                    posted_at = None
                    if hasattr(entry, "published"):
                        try:
                            posted_at = parsedate_to_datetime(entry.published).replace(tzinfo=None)
                        except Exception:
                            posted_at = self._parse_posted_at(entry.published)

                    if not self._is_recent(posted_at, max_age_hours):
                        continue

                    # Extract job ID from link
                    link = entry.link or ""
                    jk_match = re.search(r"jk=([a-f0-9]+)", link)
                    job_id = jk_match.group(1) if jk_match else link[-16:]

                    # Company from title: "Title - Company - Location"
                    title_parts = entry.title.split(" - ") if hasattr(entry, "title") else []
                    title = title_parts[0].strip() if title_parts else entry.get("title", "")
                    company = title_parts[1].strip() if len(title_parts) > 1 else "Unknown"
                    location = title_parts[2].strip() if len(title_parts) > 2 else ""

                    # Description
                    summary = entry.get("summary", "")
                    soup = BeautifulSoup(summary, "html.parser")
                    description = soup.get_text(separator="\n", strip=True)

                    is_remote = "remote" in description.lower() or "remote" in title.lower() or "remote" in location.lower()

                    jobs.append({
                        "job_id": f"indeed_{job_id}",
                        "title": title,
                        "company": company,
                        "location": location,
                        "remote": is_remote,
                        "source": "indeed",
                        "job_url": link,
                        "apply_url": link,
                        "description": description,
                        "posted_at": posted_at,
                    })
                except Exception as e:
                    logger.debug(f"Error parsing Indeed entry: {e}")
        except Exception as e:
            logger.error(f"Indeed RSS parse error: {e}")

        logger.info(f"Indeed [{keyword} @ {location}]: {len(jobs)} recent jobs")
        return jobs
