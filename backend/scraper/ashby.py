"""
Ashby ATS direct scraper.

Ashby is the ATS of choice for many elite tech companies: Linear, Retool,
Cursor, Notion (some roles), Vercel, Loom, Figma (some), Scale AI,
Anthropic, OpenAI, Perplexity, and fast-growing YC startups.

Strategy: Ashby exposes a public GraphQL endpoint per company. Jobs posted
here appear before LinkedIn aggregates them — often by 12-48 hours.

Endpoint: POST https://jobs.ashbyhq.com/api/non-user-graphql
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from .base import BaseScraper

logger = logging.getLogger(__name__)

ASHBY_COMPANIES = [
    # Top-tier tech
    "anthropic", "openai", "perplexity-ai", "linear", "retool",
    "cursor", "vercel", "railway", "planetscale", "neon",
    # YC / fast-growth
    "arc", "loom", "mercury-technologies", "ramp", "rippling",
    "deel", "brex", "descript", "replit", "resend",
    # AI / ML tools
    "weights-biases", "modal-labs", "anyscale", "together-ai",
    "cohere", "hugging-face", "mistral-ai",
    # Infrastructure
    "turso", "supabase", "hasura", "convex", "trigger-dev",
    "inngest", "temporal-technologies",
]

_GQL_QUERY = """
query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
  jobBoard: jobBoardWithTeams(
    organizationHostedJobsPageName: $organizationHostedJobsPageName
  ) {
    jobPostings {
      id
      title
      teamName
      locationName
      isRemote
      employmentType
      publishedDate
      descriptionHtml
      externalLink
    }
  }
}
"""


class AshbyScraper(BaseScraper):
    """Scrapes Ashby-powered job boards via public GraphQL API."""

    GQL_URL = "https://jobs.ashbyhq.com/api/non-user-graphql"

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
        companies = target_companies or ASHBY_COMPANIES
        all_jobs = []

        for company in companies:
            try:
                jobs = await self._scrape_company(
                    company, keywords, locations, max_age_hours, remote_only
                )
                all_jobs.extend(jobs)
            except Exception as e:
                logger.debug(f"Ashby [{company}] error: {e}")

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
        import asyncio
        import random

        session = await self._get_session()
        session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://jobs.ashbyhq.com",
            "Referer": f"https://jobs.ashbyhq.com/{company}",
        })

        payload = {
            "operationName": "ApiJobBoardWithTeams",
            "query": _GQL_QUERY,
            "variables": {"organizationHostedJobsPageName": company},
        }

        await asyncio.sleep(random.uniform(1.0, 2.5))
        try:
            resp = await session.post(self.GQL_URL, json=payload, timeout=20.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.debug(f"Ashby GQL error [{company}]: {e}")
            return []

        postings = (
            data.get("data", {})
            .get("jobBoard", {})
            .get("jobPostings", [])
        ) or []

        jobs = []
        for item in postings:
            try:
                title = item.get("title", "")
                if not title:
                    continue

                # Keyword filter
                team = item.get("teamName", "") or ""
                desc_html = item.get("descriptionHtml", "") or ""
                searchable = f"{title} {team} {desc_html[:400]}".lower()
                if not any(kw.lower() in searchable for kw in keywords):
                    continue

                location = item.get("locationName", "") or ""
                is_remote = item.get("isRemote", False) or "remote" in location.lower()

                if remote_only and not is_remote:
                    continue

                if locations and not is_remote:
                    if not any(loc.lower() in location.lower() for loc in locations):
                        continue

                # Parse publishedDate (ISO string)
                published = item.get("publishedDate", "")
                posted_at = None
                if published:
                    try:
                        posted_at = datetime.fromisoformat(
                            published.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    except Exception:
                        pass

                if posted_at and not self._is_recent(posted_at, max_age_hours):
                    continue

                uid = item.get("id", "")
                ext_link = item.get("externalLink") or f"https://jobs.ashbyhq.com/{company}/{uid}"

                # Strip HTML from description
                from bs4 import BeautifulSoup
                description = (
                    BeautifulSoup(desc_html, "html.parser").get_text("\n", strip=True)
                    if desc_html else ""
                )

                emp_type = (item.get("employmentType") or "FullTime").lower()
                type_map = {
                    "fulltime": "full-time", "full_time": "full-time",
                    "parttime": "part-time", "part_time": "part-time",
                    "contract": "contract", "contractor": "contract",
                    "intern": "internship", "internship": "internship",
                }
                job_type = type_map.get(emp_type.replace("-", ""), "full-time")

                jobs.append({
                    "job_id": f"ashby_{uid}",
                    "title": title,
                    "company": company.replace("-", " ").title(),
                    "location": location or ("Remote" if is_remote else "Unknown"),
                    "remote": is_remote,
                    "job_type": job_type,
                    "source": "ashby",
                    "job_url": ext_link,
                    "apply_url": ext_link,
                    "description": description[:10000],
                    "posted_at": posted_at,
                    "salary": None,
                })
            except Exception as e:
                logger.debug(f"Ashby parse error [{company}/{item.get('id')}]: {e}")

        return jobs
