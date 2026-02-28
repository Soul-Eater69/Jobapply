"""
Hiring Signal Detector.

Detects companies that are *about to hire* before a role is ever posted —
based on observable signals: funding rounds, headcount growth, leadership
changes, and company-specific "we're hiring" signals.

This is "Tier 3" in the proactive sourcing strategy:
  Tier 1: ATS direct scraping (hours before LinkedIn)
  Tier 2: Company watchlist (real-time for target companies)
  Tier 3: Signal detection (predict roles before they're posted)
  Tier 4: Direct outreach (bypass postings entirely)

Signals detected:
  - Recent funding rounds (Series A/B/C, growth capital)
  - Rapid LinkedIn headcount growth
  - New executive hires (VP Eng, CTO, Head of Product)
  - Company is on hiring sprees (many new JDs across departments)
  - Company just launched a new product/feature (engineering surge predicted)
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional

import anthropic

from ..config import settings

logger = logging.getLogger(__name__)

_SIGNAL_PROMPT = """\
You are a talent intelligence analyst identifying companies that are likely to
hire soon based on publicly observable signals.

## Target Companies
{companies}

## User's Target Role
Keywords: {keywords}
Experience Level: {experience}

For each company, assess current hiring signals you know about:
1. Recent funding (last 12 months) — amount, stage
2. Headcount growth trajectory (growing fast / stable / contracting)
3. Recent executive hires that suggest team expansion
4. Product launches or major announcements suggesting engineering surge
5. Overall hiring signal strength (high / medium / low / none)

Return a JSON array (no markdown), one object per company that has a signal:
[
  {{
    "company": "<name>",
    "signal_strength": "<high|medium|low>",
    "signal_type": "<funding|headcount|exec_hire|product_launch|multiple>",
    "signal_summary": "<1-2 sentences: what's happening at this company>",
    "predicted_roles": ["<role1>", "<role2>"],
    "outreach_urgency": "<now|soon|monitor>",
    "linkedin_company_url": "<if known, else empty string>"
  }}
]

Only include companies with at least a "low" signal. If you have no signal
data for a company, omit it entirely. Use your training data knowledge.
"""


class HiringSignalDetector:
    """
    Uses Claude to identify companies showing hiring signals
    before they post roles publicly.
    """

    def __init__(self):
        self._client: Optional[anthropic.AsyncAnthropic] = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._client

    async def detect(
        self,
        companies: List[str],
        keywords: List[str],
        experience_level: Optional[str] = None,
    ) -> List[dict]:
        """
        Analyze a list of companies for hiring signals.

        Returns list of companies with active hiring signals, sorted by
        signal strength (high first).
        """
        if not companies or not settings.ANTHROPIC_API_KEY:
            return []

        # Batch in groups of 20 to stay within token limits
        all_results = []
        for i in range(0, len(companies), 20):
            batch = companies[i:i + 20]
            results = await self._analyze_batch(batch, keywords, experience_level)
            all_results.extend(results)

        # Sort by signal strength
        order = {"high": 0, "medium": 1, "low": 2}
        all_results.sort(key=lambda x: order.get(x.get("signal_strength", "low"), 3))
        return all_results

    async def _analyze_batch(
        self,
        companies: List[str],
        keywords: List[str],
        experience_level: Optional[str],
    ) -> List[dict]:
        prompt = _SIGNAL_PROMPT.format(
            companies="\n".join(f"- {c}" for c in companies),
            keywords=", ".join(keywords),
            experience=experience_level or "any",
        )

        try:
            client = self._get_client()
            msg = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Signal detector error: {e}")
            return []

    def format_for_broadcast(self, signals: List[dict]) -> List[dict]:
        """Format signals for WebSocket broadcast to the frontend."""
        return [
            {
                "company": s["company"],
                "signal": s.get("signal_summary", ""),
                "strength": s.get("signal_strength", "low"),
                "urgency": s.get("outreach_urgency", "monitor"),
                "predicted_roles": s.get("predicted_roles", []),
            }
            for s in signals
        ]
