"""
Lever ATS direct scraper.

Lever powers job boards for companies like Netflix, Atlassian, Spotify, Shopify,
Twilio, Duolingo, Figma (some roles), and thousands of high-growth startups.

Strategy: Hit the public Lever REST API directly — jobs appear here *before*
LinkedIn/Indeed aggregate them, giving a 2-24 hour first-mover advantage.

API:  https://api.lever.co/v0/postings/{company}?mode=json&state=published
Docs: https://github.com/lever/postings-api
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from .base import BaseScraper

logger = logging.getLogger(__name__)

# Curated list of companies known to use Lever.
# Users can override via target_companies parameter.
LEVER_COMPANIES = [
    # Big tech / known
    "netflix", "shopify", "twilio", "atlassian", "duolingo",
    "squarespace", "momentive", "benchling", "thumbtack",
    # High-growth startups
    "linear", "retool", "runway", "mercoa", "anyscale",
    "scale-ai", "weights-biases", "prefect", "hex",
    "modal", "superconductive", "datasette", "dbt-labs",
    # Finance / fintech
    "brex", "mercury", "ramp", "sardine", "unit",
    # Healthcare / biotech
    "openevidence", "recursionpharma", "tempus",
    # Infrastructure / devtools
    "pulumi", "temporal", "dagster-labs", "buildkite", "meroxa",
]


class LeverScraper(BaseScraper):
    """Scrapes Lever-powered job boards directly via public REST API."""

    BASE = "https://api.lever.co/v0/postings"

    async def search_jobs(
        self,
        keywords: List[str],
        locations: List[str],
        max_age_hours: int = 6,
        remote_only: bool = False,
        job_types: Optional[List[str]] = None,
        experience_levels: Optional[List[str]] = None,
        target_companies: Optional[List[str]] = None,
        **kwargs,
    ) -> List[dict]:
        companies = target_companies or LEVER_COMPANIES
        all_jobs = []

        for company in companies:
            try:
                jobs = await self._scrape_company(
                    company, keywords, locations, max_age_hours, remote_only
                )
                all_jobs.extend(jobs)
            except Exception as e:
                logger.debug(f"Lever [{company}] error: {e}")

        # Deduplicate
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
        locations: List[str],
        max_age_hours: int,
        remote_only: bool,
    ) -> List[dict]:
        url = f"{self.BASE}/{company}"
        data = await self._fetch_json(url, params={"mode": "json", "state": "published"})
        if not data or not isinstance(data, list):
            return []

        jobs = []
        for item in data:
            try:
                title = item.get("text", "")
                if not title:
                    continue

                # Keyword filter
                categories = item.get("categories", {})
                commitment = categories.get("commitment", "")
                team = categories.get("team", "")
                description_plain = item.get("descriptionPlain", "") or ""
                searchable = f"{title} {team} {description_plain[:500]}".lower()

                if not any(kw.lower() in searchable for kw in keywords):
                    continue

                # Location
                location = categories.get("location", "") or item.get("workplaceType", "")
                is_remote = (
                    "remote" in location.lower()
                    or item.get("workplaceType", "").lower() == "remote"
                )
                if remote_only and not is_remote:
                    continue

                # Location match (if not remote)
                if locations and not is_remote:
                    loc_lower = location.lower()
                    if not any(loc.lower() in loc_lower for loc in locations):
                        continue

                # Timing — Lever returns createdAt as Unix ms
                created_at_ms = item.get("createdAt", 0)
                if created_at_ms:
                    posted_at = datetime.fromtimestamp(created_at_ms / 1000, tz=timezone.utc).replace(tzinfo=None)
                else:
                    posted_at = None

                if posted_at and not self._is_recent(posted_at, max_age_hours):
                    continue

                uid = item.get("id", "")
                job_url = item.get("hostedUrl", f"https://jobs.lever.co/{company}/{uid}")

                # Job type mapping
                type_map = {
                    "full-time": "full-time",
                    "part-time": "part-time",
                    "contract": "contract",
                    "internship": "internship",
                }
                job_type = type_map.get(commitment.lower(), commitment or "full-time")

                # Salary (Lever doesn't surface this in v0 API — leave None)
                jobs.append({
                    "job_id": f"lever_{uid}",
                    "title": title,
                    "company": item.get("company", company.replace("-", " ").title()),
                    "location": location or "Unknown",
                    "remote": is_remote,
                    "job_type": job_type,
                    "source": "lever",
                    "job_url": job_url,
                    "apply_url": job_url,
                    "description": description_plain[:10000],
                    "posted_at": posted_at,
                    "salary": None,
                })
            except Exception as e:
                logger.debug(f"Lever parse error [{company}]: {e}")

        return jobs
