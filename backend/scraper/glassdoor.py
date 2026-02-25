import logging
import re
import json
from datetime import datetime
from typing import List, Optional
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)


class GlassdoorScraper(BaseScraper):
    SEARCH_URL = "https://www.glassdoor.com/Job/jobs.htm"
    API_URL = "https://www.glassdoor.com/graph"

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
                jobs = await self._search(keyword, location, max_age_hours, remote_only)
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
        remote_only: bool,
    ) -> List[dict]:
        params = {
            "sc.keyword": keyword,
            "locT": "C" if not remote_only else "N",
            "locId": "",
            "jobType": "",
            "fromAge": "1",  # 1 day - smallest option, we filter further
            "minSalary": "",
            "includeNoSalaryJobs": "true",
            "radius": "25",
            "cityId": "-1",
            "minRating": "0.0",
            "industryId": "-1",
            "sgocId": "-1",
            "seniorityType": "all",
            "companyId": "-1",
            "employerSizes": "0",
            "applicationType": "0",
            "remoteWorkType": "1" if remote_only else "0",
        }

        if not remote_only and location:
            params["locT"] = "C"
            params["suggestChosen"] = "false"
            params["clickSource"] = "searchBtn"
            params["typedKeyword"] = keyword

        html = await self._fetch(self.SEARCH_URL, params=params)
        if not html:
            return []

        jobs = []
        soup = BeautifulSoup(html, "html.parser")

        # Try to find embedded JSON with job data
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                        job = self._parse_ld_json(item, max_age_hours)
                        if job:
                            jobs.append(job)
                elif isinstance(data, dict):
                    job = self._parse_ld_json(data, max_age_hours)
                    if job:
                        jobs.append(job)
            except Exception:
                pass

        # Fall back to HTML parsing
        if not jobs:
            job_cards = soup.find_all("li", attrs={"data-test": "jobListing"})
            for card in job_cards:
                job = self._parse_html_card(card, max_age_hours)
                if job:
                    jobs.append(job)

        logger.info(f"Glassdoor [{keyword} @ {location}]: {len(jobs)} recent jobs")
        return jobs

    def _parse_ld_json(self, data: dict, max_age_hours: int) -> Optional[dict]:
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
        job_id = re.search(r"jobListingId=(\d+)", job_url)
        job_id = job_id.group(1) if job_id else job_url[-12:]

        location_data = data.get("jobLocation", {})
        if isinstance(location_data, list):
            location_data = location_data[0] if location_data else {}
        address = location_data.get("address", {})
        location = f"{address.get('addressLocality', '')}, {address.get('addressRegion', '')}".strip(", ")

        description = BeautifulSoup(data.get("description", ""), "html.parser").get_text(separator="\n", strip=True)

        return {
            "job_id": f"glassdoor_{job_id}",
            "title": data.get("title", ""),
            "company": data.get("hiringOrganization", {}).get("name", "Unknown"),
            "location": location,
            "remote": "remote" in description.lower(),
            "source": "glassdoor",
            "job_url": job_url,
            "apply_url": job_url,
            "description": description,
            "salary": data.get("baseSalary", {}).get("value", {}).get("description"),
            "posted_at": posted_at,
        }

    def _parse_html_card(self, card, max_age_hours: int) -> Optional[dict]:
        try:
            title_el = card.find("a", attrs={"data-test": "job-title"})
            title = title_el.get_text(strip=True) if title_el else ""
            job_url = title_el.get("href", "") if title_el else ""
            if job_url and not job_url.startswith("http"):
                job_url = "https://www.glassdoor.com" + job_url

            company_el = card.find("span", attrs={"data-test": "employer-name"})
            company = company_el.get_text(strip=True) if company_el else ""

            loc_el = card.find("span", attrs={"data-test": "emp-location"})
            location = loc_el.get_text(strip=True) if loc_el else ""

            age_el = card.find("div", attrs={"data-test": "job-age"})
            age_text = age_el.get_text(strip=True) if age_el else ""
            posted_at = self._parse_posted_at(age_text)

            if not self._is_recent(posted_at, max_age_hours):
                return None

            job_id = re.search(r"jobListingId=(\d+)", job_url)
            job_id = job_id.group(1) if job_id else job_url[-12:]

            return {
                "job_id": f"glassdoor_{job_id}",
                "title": title,
                "company": company,
                "location": location,
                "remote": "remote" in location.lower() or "remote" in title.lower(),
                "source": "glassdoor",
                "job_url": job_url,
                "apply_url": job_url,
                "description": "",
                "posted_at": posted_at,
            }
        except Exception as e:
            logger.debug(f"Error parsing Glassdoor card: {e}")
            return None
