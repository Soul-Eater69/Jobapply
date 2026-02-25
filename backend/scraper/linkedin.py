import logging
import re
import json
from datetime import datetime
from typing import List, Optional
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)

LINKEDIN_JOBS_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
LINKEDIN_JOB_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

EXPERIENCE_MAP = {
    "entry": "1",
    "mid": "2",
    "senior": "3",
    "director": "4",
    "executive": "5",
    "internship": "1",
}

JOB_TYPE_MAP = {
    "full-time": "F",
    "part-time": "P",
    "contract": "C",
    "temporary": "T",
    "internship": "I",
    "volunteer": "V",
    "other": "O",
}


class LinkedInScraper(BaseScraper):

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
                jobs = await self._search(
                    keyword, location, max_age_hours, remote_only, job_types, experience_levels
                )
                all_jobs.extend(jobs)

        # Deduplicate by job_id
        seen = set()
        unique = []
        for j in all_jobs:
            if j["job_id"] not in seen:
                seen.add(j["job_id"])
                unique.append(j)

        return unique

    async def _search(
        self,
        keyword: str,
        location: str,
        max_age_hours: int,
        remote_only: bool,
        job_types: Optional[List[str]],
        experience_levels: Optional[List[str]],
    ) -> List[dict]:
        jobs = []
        start = 0

        # Build f_TPR for time filter (r3600 = last 1 hour)
        time_filter = f"r{max_age_hours * 3600}"

        params = {
            "keywords": keyword,
            "location": location,
            "f_TPR": time_filter,
            "start": start,
            "count": 25,
        }

        if remote_only:
            params["f_WT"] = "2"  # Remote

        if job_types:
            f_jt = ",".join(JOB_TYPE_MAP.get(jt.lower(), "F") for jt in job_types)
            params["f_JT"] = f_jt

        if experience_levels:
            f_el = ",".join(EXPERIENCE_MAP.get(el.lower(), "2") for el in experience_levels)
            params["f_E"] = f_el

        html = await self._fetch(LINKEDIN_JOBS_URL, params=params)
        if not html:
            return jobs

        soup = BeautifulSoup(html, "html.parser")
        job_cards = soup.find_all("div", class_=re.compile(r"base-card"))

        for card in job_cards:
            try:
                job = self._parse_card(card)
                if not job:
                    continue

                # Only keep recent jobs
                if not self._is_recent(job.get("posted_at"), max_age_hours):
                    continue

                # Fetch description
                detail = await self._fetch_detail(job["job_id"])
                if detail:
                    job["description"] = detail.get("description", "")
                    job["apply_url"] = detail.get("apply_url") or job["job_url"]

                jobs.append(job)
            except Exception as e:
                logger.debug(f"Error parsing LinkedIn card: {e}")

        logger.info(f"LinkedIn [{keyword} @ {location}]: {len(jobs)} recent jobs")
        return jobs

    def _parse_card(self, card) -> Optional[dict]:
        # Job ID
        entity_urn = card.get("data-entity-urn", "")
        job_id_match = re.search(r":(\d+)$", entity_urn)
        if not job_id_match:
            return None
        job_id = job_id_match.group(1)

        # Title
        title_el = card.find("h3", class_=re.compile(r"base-search-card__title"))
        title = title_el.get_text(strip=True) if title_el else ""

        # Company
        company_el = card.find("h4", class_=re.compile(r"base-search-card__subtitle"))
        company = company_el.get_text(strip=True) if company_el else ""

        # Location
        loc_el = card.find("span", class_=re.compile(r"job-search-card__location"))
        location = loc_el.get_text(strip=True) if loc_el else ""

        # Posted time
        time_el = card.find("time")
        posted_str = time_el.get("datetime", "") if time_el else ""
        posted_text = time_el.get_text(strip=True) if time_el else ""

        posted_at = None
        if posted_str:
            try:
                posted_at = datetime.fromisoformat(posted_str.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                posted_at = self._parse_posted_at(posted_text)
        else:
            posted_at = self._parse_posted_at(posted_text)

        # Job URL
        link_el = card.find("a", class_=re.compile(r"base-card__full-link"))
        if not link_el:
            link_el = card.find("a", href=re.compile(r"/jobs/view/"))
        job_url = link_el.get("href", "").split("?")[0] if link_el else ""
        if job_url and not job_url.startswith("http"):
            job_url = "https://www.linkedin.com" + job_url

        # Remote detection
        is_remote = "remote" in location.lower() or "remote" in title.lower()

        return {
            "job_id": f"linkedin_{job_id}",
            "title": title,
            "company": company,
            "location": location,
            "remote": is_remote,
            "source": "linkedin",
            "job_url": job_url,
            "posted_at": posted_at,
        }

    async def _fetch_detail(self, job_id: str) -> Optional[dict]:
        raw_id = job_id.replace("linkedin_", "")
        url = LINKEDIN_JOB_DETAIL_URL.format(job_id=raw_id)
        html = await self._fetch(url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Description
        desc_el = soup.find("div", class_=re.compile(r"show-more-less-html__markup"))
        if not desc_el:
            desc_el = soup.find("section", class_=re.compile(r"description"))
        description = desc_el.get_text(separator="\n", strip=True) if desc_el else ""

        # Apply URL
        apply_btn = soup.find("a", class_=re.compile(r"apply-button"))
        apply_url = apply_btn.get("href") if apply_btn else None

        # Salary
        salary_el = soup.find("span", class_=re.compile(r"salary"))
        salary = salary_el.get_text(strip=True) if salary_el else None

        # Job type
        criteria = soup.find_all("span", class_=re.compile(r"description__job-criteria-text"))
        job_type = None
        for c in criteria:
            text = c.get_text(strip=True).lower()
            if any(t in text for t in ["full-time", "part-time", "contract", "temporary"]):
                job_type = c.get_text(strip=True)
                break

        return {
            "description": description,
            "apply_url": apply_url,
            "salary": salary,
            "job_type": job_type,
        }
