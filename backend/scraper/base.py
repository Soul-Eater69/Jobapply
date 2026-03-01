import asyncio
import random
import logging
from datetime import datetime, timedelta
from typing import List, Optional
import httpx

logger = logging.getLogger(__name__)

# Realistic browser user agents pool
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
]

ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9,en-US;q=0.8",
    "en-US,en;q=0.8",
    "en,en-US;q=0.9",
]


class BaseScraper:
    def __init__(self):
        self.session: Optional[httpx.AsyncClient] = None
        self._ua = random.choice(USER_AGENTS)

    def _get_headers(self) -> dict:
        return {
            "User-Agent": self._ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": random.choice(ACCEPT_LANGUAGES),
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    async def _get_session(self) -> httpx.AsyncClient:
        if not self.session or self.session.is_closed:
            from ..config import settings
            proxies = None
            if settings.PROXY_LIST:
                proxy = random.choice(settings.PROXY_LIST)
                proxies = {"http://": proxy, "https://": proxy}

            self.session = httpx.AsyncClient(
                headers=self._get_headers(),
                follow_redirects=True,
                timeout=30.0,
                proxies=proxies,
            )
        return self.session

    async def _fetch(self, url: str, params: dict = None, retry: int = 3) -> Optional[str]:
        session = await self._get_session()
        for attempt in range(retry):
            try:
                # Random delay to avoid rate limiting
                await asyncio.sleep(random.uniform(1.5, 4.0))
                resp = await session.get(url, params=params)
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = (attempt + 1) * 10 + random.uniform(5, 15)
                    logger.warning(f"Rate limited on {url}. Waiting {wait:.0f}s...")
                    await asyncio.sleep(wait)
                    # Rotate UA on retry
                    self._ua = random.choice(USER_AGENTS)
                    session.headers.update({"User-Agent": self._ua})
                elif e.response.status_code in (403, 401):
                    logger.warning(f"Access denied on {url}")
                    return None
                else:
                    logger.error(f"HTTP {e.response.status_code} on {url}")
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"Fetch error on {url}: {e}")
                await asyncio.sleep(2 ** attempt)
        return None

    async def _fetch_json(self, url: str, params: dict = None) -> Optional[dict]:
        import gzip as _gzip
        import json as _json
        session = await self._get_session()
        session.headers.update({
            "Accept": "application/json, text/plain, */*",
            # Don't advertise compression for JSON calls; some servers return raw gzip
            # that httpx won't auto-decompress when the header was set manually.
            "Accept-Encoding": "identity",
        })
        try:
            await asyncio.sleep(random.uniform(1.0, 3.0))
            resp = await session.get(url, params=params)
            resp.raise_for_status()
            content = resp.content
            # Fallback: decompress if server ignored Accept-Encoding and sent gzip anyway
            if content[:2] == b'\x1f\x8b':
                content = _gzip.decompress(content)
            return _json.loads(content)
        except Exception as e:
            logger.error(f"JSON fetch error {url}: {e}")
            return None

    def _parse_posted_at(self, time_str: str) -> Optional[datetime]:
        """Parse relative time strings like '30 minutes ago', '1 hour ago'"""
        if not time_str:
            return None
        time_str = time_str.lower().strip()
        now = datetime.utcnow()

        try:
            if "just now" in time_str or "moment" in time_str:
                return now
            if "minute" in time_str:
                n = int(''.join(filter(str.isdigit, time_str)) or "1")
                return now - timedelta(minutes=n)
            if "hour" in time_str:
                n = int(''.join(filter(str.isdigit, time_str)) or "1")
                return now - timedelta(hours=n)
            if "day" in time_str:
                n = int(''.join(filter(str.isdigit, time_str)) or "1")
                return now - timedelta(days=n)
            if "week" in time_str:
                n = int(''.join(filter(str.isdigit, time_str)) or "1")
                return now - timedelta(weeks=n)
            if "month" in time_str:
                n = int(''.join(filter(str.isdigit, time_str)) or "1")
                return now - timedelta(days=n * 30)
        except Exception:
            pass

        return None

    def _is_recent(self, posted_at: Optional[datetime], max_age_hours: int = 1) -> bool:
        if not posted_at:
            return False
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        return posted_at >= cutoff

    async def search_jobs(self, **kwargs) -> List[dict]:
        raise NotImplementedError

    async def close(self):
        if self.session and not self.session.is_closed:
            await self.session.aclose()
