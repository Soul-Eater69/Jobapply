import asyncio
import gzip as _gzip
import json as _json
import logging
import random
from datetime import datetime
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)

# Only warn once per process if the API stays blocked
_dice_warned = False


class DiceScraper(BaseScraper):
    API_URL = "https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search"

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
        global _dice_warned

        params = {
            "q": keyword,
            "countryCode2": "US",
            "radius": "30",
            "radiusUnit": "miles",
            "page": "1",
            "pageSize": "50",
            "facets": "employmentType|postedDate|workFromHomeAvailability|employerType|easyApply|isRemote",
            "filters.postedDate": "ONE_DAY",
            "fields": (
                "id,jobId,guid,summary,title,postedDate,modifiedDate,jobLocation,salary,clientBrandId,"
                "companyPageUrl,companyLogoUrl,score,easyApply,employerId,employerType,"
                "employmentType,hiringOrganization,jobMeta,language,location,workFromHomeAvailability,"
                "workplaceTypes,country,externalApplyLink"
            ),
            "culture": "en",
            "recommendations": "true",
            "interstitialCount": "0",
            "fj": "true",
            "includeRemote": "true",
        }

        if location.lower() == "remote":
            params["filters.workFromHomeAvailability"] = "Remote"
        else:
            params["location"] = location

        session = await self._get_session()

        # Step 1: Prime session — visit dice.com/jobs so the server sets cookies.
        # Browsers always do this before hitting the internal API.
        try:
            await asyncio.sleep(random.uniform(0.8, 1.5))
            await session.get(
                "https://www.dice.com/jobs",
                headers={
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;"
                        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
                    ),
                    "Accept-Encoding": "gzip, deflate, br",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "Cache-Control": "max-age=0",
                },
            )
        except Exception:
            pass  # Non-fatal; proceed with whatever cookies we have

        # Step 2: Hit the internal search API as an XHR from dice.com
        await asyncio.sleep(random.uniform(0.5, 1.2))
        try:
            resp = await session.get(
                self.API_URL,
                params=params,
                headers={
                    "x-api-key": "1YAt0R9wBg4WI4eScpvxnil34sSiau5A",
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Encoding": "identity",
                    "Origin": "https://www.dice.com",
                    "Referer": "https://www.dice.com/jobs",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-site",
                    "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                },
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 403:
                if not _dice_warned:
                    logger.warning(
                        "Dice API returned 403 — the endpoint may be IP-restricted "
                        "(common in cloud/Docker environments). Dice results will be skipped. "
                        "Add a residential proxy via PROXY_LIST in .env to bypass this."
                    )
                    _dice_warned = True
            else:
                logger.error(f"Dice API HTTP {code} for '{keyword}'")
            return []
        except Exception as e:
            logger.error(f"Dice fetch error for '{keyword}': {e}")
            return []

        # Step 3: Decode response (handle unexpected gzip just in case)
        content = resp.content
        if content[:2] == b"\x1f\x8b":
            content = _gzip.decompress(content)

        try:
            data = _json.loads(content)
        except Exception as e:
            logger.error(f"Dice JSON parse error: {e}")
            return []

        jobs = []
        for item in data.get("data", []):
            try:
                job = self._parse_item(item, max_age_hours)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"Error parsing Dice item: {e}")

        logger.info(f"Dice [{keyword} @ {location}]: {len(jobs)} recent jobs")
        return jobs

    def _parse_item(self, item: dict, max_age_hours: int) -> Optional[dict]:
        posted_str = item.get("postedDate", "")
        posted_at = None
        if posted_str:
            try:
                posted_at = datetime.fromisoformat(posted_str.replace("Z", ""))
            except Exception:
                posted_at = self._parse_posted_at(posted_str)

        if not self._is_recent(posted_at, max_age_hours):
            return None

        job_id = item.get("id") or item.get("jobId") or item.get("guid", "")
        title = item.get("title", "")

        hiring_org = item.get("hiringOrganization", {})
        company = hiring_org.get("name", item.get("clientBrandId", "Unknown"))

        location_data = item.get("jobLocation", [{}])
        if isinstance(location_data, list) and location_data:
            location_data = location_data[0]
        location = location_data.get("displayName", item.get("location", ""))

        is_remote = (
            item.get("workFromHomeAvailability") == "Remote"
            or item.get("isRemote", False)
            or "remote" in location.lower()
        )

        job_url = f"https://www.dice.com/jobs/{job_id}"
        apply_url = item.get("externalApplyLink") or job_url

        description = item.get("summary", "")
        if description:
            description = BeautifulSoup(description, "html.parser").get_text(
                separator="\n", strip=True
            )

        salary_info = item.get("salary")
        salary = None
        if isinstance(salary_info, dict):
            salary = salary_info.get("description") or salary_info.get("range", {}).get(
                "description"
            )
        elif isinstance(salary_info, str):
            salary = salary_info

        emp_type = item.get("employmentType", [])
        job_type = emp_type[0] if isinstance(emp_type, list) and emp_type else None

        return {
            "job_id": f"dice_{job_id}",
            "title": title,
            "company": company,
            "location": location,
            "remote": is_remote,
            "source": "dice",
            "job_url": job_url,
            "apply_url": apply_url,
            "description": description,
            "salary": salary,
            "job_type": job_type,
            "posted_at": posted_at,
        }
