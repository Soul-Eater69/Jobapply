"""ZipRecruiter scraper — uses their public search endpoint."""
import logging
import re
import json
from datetime import datetime
from typing import List, Optional
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)


class ZipRecruiterScraper(BaseScraper):
    SEARCH_URL = "https://www.ziprecruiter.com/jobs-search"

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
            for location in (["remote"] if remote_only else locations):
                jobs = await self._search(keyword, location, max_age_hours, job_types)
                all_jobs.extend(jobs)

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
        job_types: Optional[List[str]],
    ) -> List[dict]:
        params = {
            "search": keyword,
            "location": location,
            "days": "1",
            "sort": "date",
            "page": "1",
        }

        if job_types:
            jt_map = {"full-time": "full_time", "part-time": "part_time", "contract": "contract"}
            params["employment_type[]"] = [jt_map.get(jt.lower(), jt) for jt in job_types]

        html = await self._fetch(self.SEARCH_URL, params=params)
        if not html:
            return []

        jobs = []
        soup = BeautifulSoup(html, "html.parser")

        # Try to extract embedded JSON-LD
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    for item in data:
                        job = self._parse_ld(item, max_age_hours)
                        if job:
                            jobs.append(job)
                elif isinstance(data, dict):
                    job = self._parse_ld(data, max_age_hours)
                    if job:
                        jobs.append(job)
            except Exception:
                pass

        # HTML fallback
        if not jobs:
            cards = soup.find_all("article", class_=re.compile(r"job_result|jobCard"))
            for card in cards:
                job = self._parse_card(card, max_age_hours)
                if job:
                    jobs.append(job)

        logger.info(f"ZipRecruiter [{keyword} @ {location}]: {len(jobs)} recent jobs")
        return jobs

    def _parse_ld(self, data: dict, max_age_hours: int) -> Optional[dict]:
        if data.get("@type") != "JobPosting":
            return None

        posted_str = data.get("datePosted", "")
        posted_at = None
        if posted_str:
            try:
                posted_at = datetime.fromisoformat(posted_str.replace("Z", ""))
            except Exception:
                pass

        if not self._is_recent(posted_at, max_age_hours):
            return None

        job_url = data.get("url", "")
        job_id = re.search(r"/j/([^/?]+)", job_url)
        job_id = job_id.group(1) if job_id else job_url[-16:]

        loc = data.get("jobLocation", {})
        if isinstance(loc, list):
            loc = loc[0] if loc else {}
        addr = loc.get("address", {})
        location = f"{addr.get('addressLocality', '')}, {addr.get('addressRegion', '')}".strip(", ")

        desc = BeautifulSoup(data.get("description", ""), "html.parser").get_text(separator="\n", strip=True)

        return {
            "job_id": f"zip_{job_id}",
            "title": data.get("title", ""),
            "company": data.get("hiringOrganization", {}).get("name", "Unknown"),
            "location": location,
            "remote": "remote" in desc.lower() or "remote" in location.lower(),
            "source": "ziprecruiter",
            "job_url": job_url,
            "apply_url": job_url,
            "description": desc,
            "salary": str(data.get("baseSalary", {}).get("value", {}).get("description", "")) or None,
            "posted_at": posted_at,
        }

    def _parse_card(self, card, max_age_hours: int) -> Optional[dict]:
        try:
            title_el = card.find("h2") or card.find("a", class_=re.compile(r"job_link"))
            title = title_el.get_text(strip=True) if title_el else ""

            link_el = card.find("a", href=re.compile(r"/job/"))
            job_url = link_el.get("href", "") if link_el else ""
            if job_url and not job_url.startswith("http"):
                job_url = "https://www.ziprecruiter.com" + job_url

            company_el = card.find(class_=re.compile(r"hiring_company|employer"))
            company = company_el.get_text(strip=True) if company_el else "Unknown"

            loc_el = card.find(class_=re.compile(r"location"))
            location = loc_el.get_text(strip=True) if loc_el else ""

            age_el = card.find(class_=re.compile(r"date|posted|ago"))
            posted_at = self._parse_posted_at(age_el.get_text(strip=True) if age_el else "")

            if not self._is_recent(posted_at, max_age_hours):
                return None

            job_id = re.search(r"/j/([^/?]+)", job_url)
            job_id = job_id.group(1) if job_id else job_url[-12:]

            return {
                "job_id": f"zip_{job_id}",
                "title": title,
                "company": company,
                "location": location,
                "remote": "remote" in location.lower() or "remote" in title.lower(),
                "source": "ziprecruiter",
                "job_url": job_url,
                "apply_url": job_url,
                "description": "",
                "posted_at": posted_at,
            }
        except Exception as e:
            logger.debug(f"ZipRecruiter card error: {e}")
            return None
