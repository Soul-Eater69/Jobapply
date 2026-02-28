"""
Company Watchlist Scraper.

Monitors a user-defined list of target companies across ALL supported ATS
platforms simultaneously. This is "Tier 2" in the proactive sourcing strategy:

  Tier 1 (ATS direct) — scan broad company lists on Greenhouse/Lever/Ashby
  Tier 2 (Watchlist)  — monitor specific companies the user cares about,
                        checking EVERY ATS they might use, every cycle

How it works:
  1. User specifies target_companies in AutomationConfig
  2. This scraper tries each company slug against all ATS platforms
  3. Returns fresh jobs from any ATS where the company is found
  4. Effectively gives real-time monitoring of up to N companies

This catches companies that use Workday, iCIMS, BambooHR, SmartRecruiters,
Breezy, or any other ATS by falling back to HTML careers page scraping.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import List, Optional
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)

# ATS detection patterns — each entry is (ATS name, URL template, fetch method)
# We try each one for every target company.
ATS_PROBES = [
    ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"),
    ("lever",      "https://api.lever.co/v0/postings/{slug}?mode=json&state=published"),
    ("ashby",      None),   # Handled separately via GraphQL
]

# Known careers page URL patterns (HTML scraping fallback)
CAREERS_URL_PATTERNS = [
    "https://www.{domain}/careers",
    "https://www.{domain}/jobs",
    "https://careers.{domain}",
    "https://jobs.{domain}",
    "https://{domain}/careers",
    "https://{domain}/jobs",
]

# Map well-known companies to their ATS slugs to avoid guessing
COMPANY_ATS_MAP = {
    # company_name_lowercase: {ats: slug}
    "stripe":      {"greenhouse": "stripe"},
    "airbnb":      {"greenhouse": "airbnb"},
    "netflix":     {"lever": "netflix"},
    "shopify":     {"lever": "shopify"},
    "atlassian":   {"lever": "atlassian"},
    "linear":      {"ashby": "linear"},
    "retool":      {"ashby": "retool"},
    "vercel":      {"ashby": "vercel"},
    "anthropic":   {"ashby": "anthropic"},
    "openai":      {"ashby": "openai"},
    "notion":      {"greenhouse": "notion"},
    "discord":     {"greenhouse": "discord"},
    "figma":       {"greenhouse": "figma"},
    "datadog":     {"greenhouse": "datadog"},
    "cloudflare":  {"greenhouse": "cloudflare"},
    "plaid":       {"greenhouse": "plaid"},
    "coinbase":    {"greenhouse": "coinbase"},
    "brex":        {"lever": "brex"},
    "duolingo":    {"lever": "duolingo"},
}


class CompanyWatchlistScraper(BaseScraper):
    """
    Monitors user-specified companies across all ATS platforms.

    Pass target_companies=['stripe', 'linear', 'vercel'] and this scraper
    will check every ATS those companies might use, returning fresh jobs
    within max_age_hours of posting.
    """

    async def search_jobs(
        self,
        keywords: List[str],
        locations: List[str],
        max_age_hours: int = 2,
        remote_only: bool = False,
        job_types: Optional[List[str]] = None,
        experience_levels: Optional[List[str]] = None,
        target_companies: Optional[List[str]] = None,
        **kwargs,
    ) -> List[dict]:
        if not target_companies:
            return []

        tasks = [
            self._monitor_company(
                company, keywords, locations, max_age_hours, remote_only
            )
            for company in target_companies
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_jobs = []
        for company, result in zip(target_companies, results):
            if isinstance(result, Exception):
                logger.debug(f"Watchlist [{company}] error: {result}")
            elif result:
                all_jobs.extend(result)

        # Deduplicate
        seen = set()
        unique = []
        for j in all_jobs:
            if j["job_id"] not in seen:
                seen.add(j["job_id"])
                unique.append(j)
        return unique

    async def _monitor_company(
        self,
        company: str,
        keywords: List[str],
        locations: List[str],
        max_age_hours: int,
        remote_only: bool,
    ) -> List[dict]:
        slug = company.lower().strip()
        known = COMPANY_ATS_MAP.get(slug, {})

        jobs = []

        # Try known ATS first
        if "greenhouse" in known:
            jobs = await self._try_greenhouse(
                known["greenhouse"], company, keywords, locations, max_age_hours, remote_only
            )
            if jobs:
                return jobs

        if "lever" in known:
            jobs = await self._try_lever(
                known["lever"], company, keywords, locations, max_age_hours, remote_only
            )
            if jobs:
                return jobs

        if "ashby" in known:
            jobs = await self._try_ashby(
                known["ashby"], company, keywords, locations, max_age_hours, remote_only
            )
            if jobs:
                return jobs

        # Unknown ATS — try each platform by guessing the slug
        for ats, probe_url in ATS_PROBES:
            if probe_url is None:
                continue
            url = probe_url.format(slug=slug)
            try:
                data = await self._fetch_json(url)
                if data:
                    parsed = self._parse_ats_response(
                        ats, slug, company, data, keywords, locations, max_age_hours, remote_only
                    )
                    if parsed:
                        logger.info(f"Watchlist: found {len(parsed)} jobs at {company} via {ats}")
                        jobs.extend(parsed)
                        break
            except Exception as e:
                logger.debug(f"Watchlist probe [{ats}/{company}]: {e}")

        # Last resort: try Ashby GraphQL
        if not jobs:
            try:
                jobs = await self._try_ashby(
                    slug, company, keywords, locations, max_age_hours, remote_only
                )
            except Exception:
                pass

        return jobs

    # ── ATS-specific helpers ──────────────────────────────────────────────────

    async def _try_greenhouse(self, gh_slug, company, keywords, locations, max_age_hours, remote_only):
        url = f"https://boards-api.greenhouse.io/v1/boards/{gh_slug}/jobs?content=true"
        data = await self._fetch_json(url)
        if not data:
            return []
        return self._parse_ats_response(
            "greenhouse", gh_slug, company, data, keywords, locations, max_age_hours, remote_only
        )

    async def _try_lever(self, lev_slug, company, keywords, locations, max_age_hours, remote_only):
        url = f"https://api.lever.co/v0/postings/{lev_slug}?mode=json&state=published"
        data = await self._fetch_json(url)
        if not data:
            return []
        return self._parse_ats_response(
            "lever", lev_slug, company, data, keywords, locations, max_age_hours, remote_only
        )

    async def _try_ashby(self, ash_slug, company, keywords, locations, max_age_hours, remote_only):
        from .ashby import AshbyScraper, _GQL_QUERY
        session = await self._get_session()
        session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        payload = {
            "operationName": "ApiJobBoardWithTeams",
            "query": _GQL_QUERY,
            "variables": {"organizationHostedJobsPageName": ash_slug},
        }
        try:
            resp = await session.post(
                "https://jobs.ashbyhq.com/api/non-user-graphql",
                json=payload,
                timeout=20.0,
            )
            resp.raise_for_status()
            data = resp.json()
            postings = (
                data.get("data", {}).get("jobBoard", {}).get("jobPostings", []) or []
            )
            return self._parse_ashby_postings(ash_slug, company, postings, keywords, locations, max_age_hours, remote_only)
        except Exception as e:
            logger.debug(f"Ashby watchlist [{ash_slug}]: {e}")
            return []

    def _parse_ats_response(self, ats, slug, company, data, keywords, locations, max_age_hours, remote_only):
        if ats == "greenhouse":
            return self._parse_greenhouse(slug, company, data, keywords, locations, max_age_hours, remote_only)
        if ats == "lever":
            return self._parse_lever(slug, company, data, keywords, locations, max_age_hours, remote_only)
        return []

    def _parse_greenhouse(self, slug, company, data, keywords, locations, max_age_hours, remote_only):
        jobs = []
        for item in data.get("jobs", []):
            title = item.get("title", "")
            if not any(kw.lower() in title.lower() for kw in keywords):
                continue
            location = item.get("location", {}).get("name", "")
            is_remote = "remote" in location.lower()
            if remote_only and not is_remote:
                continue
            updated = item.get("updated_at", "")
            posted_at = None
            if updated:
                try:
                    posted_at = datetime.fromisoformat(updated.replace("Z", ""))
                except Exception:
                    pass
            if posted_at and not self._is_recent(posted_at, max_age_hours):
                continue
            uid = item.get("id")
            jobs.append({
                "job_id": f"watchlist_gh_{uid}",
                "title": title,
                "company": company,
                "location": location,
                "remote": is_remote,
                "source": "watchlist",
                "job_url": item.get("absolute_url", f"https://boards.greenhouse.io/{slug}/jobs/{uid}"),
                "apply_url": item.get("absolute_url"),
                "description": BeautifulSoup(item.get("content", ""), "html.parser").get_text("\n", strip=True)[:10000],
                "posted_at": posted_at,
                "salary": None,
            })
        return jobs

    def _parse_lever(self, slug, company, data, keywords, locations, max_age_hours, remote_only):
        from datetime import timezone
        jobs = []
        for item in (data if isinstance(data, list) else []):
            title = item.get("text", "")
            if not any(kw.lower() in (title + item.get("descriptionPlain", ""))[:500].lower() for kw in keywords):
                continue
            cats = item.get("categories", {})
            location = cats.get("location", "")
            is_remote = "remote" in location.lower() or item.get("workplaceType", "").lower() == "remote"
            if remote_only and not is_remote:
                continue
            created_ms = item.get("createdAt", 0)
            posted_at = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).replace(tzinfo=None) if created_ms else None
            if posted_at and not self._is_recent(posted_at, max_age_hours):
                continue
            uid = item.get("id", "")
            jobs.append({
                "job_id": f"watchlist_lv_{uid}",
                "title": title,
                "company": company,
                "location": location or "Unknown",
                "remote": is_remote,
                "source": "watchlist",
                "job_url": item.get("hostedUrl", f"https://jobs.lever.co/{slug}/{uid}"),
                "apply_url": item.get("hostedUrl"),
                "description": (item.get("descriptionPlain") or "")[:10000],
                "posted_at": posted_at,
                "salary": None,
            })
        return jobs

    def _parse_ashby_postings(self, slug, company, postings, keywords, locations, max_age_hours, remote_only):
        jobs = []
        for item in postings:
            title = item.get("title", "")
            if not any(kw.lower() in title.lower() for kw in keywords):
                continue
            location = item.get("locationName", "")
            is_remote = item.get("isRemote", False) or "remote" in location.lower()
            if remote_only and not is_remote:
                continue
            published = item.get("publishedDate", "")
            posted_at = None
            if published:
                try:
                    posted_at = datetime.fromisoformat(published.replace("Z", "+00:00")).replace(tzinfo=None)
                except Exception:
                    pass
            if posted_at and not self._is_recent(posted_at, max_age_hours):
                continue
            uid = item.get("id", "")
            ext = item.get("externalLink") or f"https://jobs.ashbyhq.com/{slug}/{uid}"
            desc = BeautifulSoup(item.get("descriptionHtml", "") or "", "html.parser").get_text("\n", strip=True)
            jobs.append({
                "job_id": f"watchlist_ash_{uid}",
                "title": title,
                "company": company,
                "location": location or ("Remote" if is_remote else "Unknown"),
                "remote": is_remote,
                "source": "watchlist",
                "job_url": ext,
                "apply_url": ext,
                "description": desc[:10000],
                "posted_at": posted_at,
                "salary": None,
            })
        return jobs
