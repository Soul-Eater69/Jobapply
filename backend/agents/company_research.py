"""
Company Research Agent.

Extracts company intelligence from the job description and Claude's knowledge
to personalize cover letters and resumes. Uses Claude Haiku for speed and cost.
"""

import json
import logging
from typing import Optional

import anthropic

from ..config import settings

logger = logging.getLogger(__name__)

_PROMPT = """\
You are a research analyst gathering intelligence about a company for a job applicant.

Company:    {company}
Job Title:  {title}
Job Source: {source}

Job Description (excerpt):
{description}

Based on the job description and your knowledge, return ONLY a JSON object:
{{
  "industry": "<primary industry>",
  "size": "<one of: startup <50 | growth 50-500 | mid-size 500-2000 | enterprise 2000+>",
  "growth_stage": "<one of: early-stage | growth | mature | public>",
  "tech_stack": ["<tech1>", "<tech2>", ...],
  "culture": "<2-3 sentences about culture/values inferred from JD>",
  "remote_policy": "<one of: remote | hybrid | on-site | unknown>",
  "recent_news": "<any notable context about this company, 1-2 sentences, or empty string>",
  "talking_points": [
    "<specific thing to mention in cover letter — be concrete>",
    "<second talking point>",
    "<third talking point>"
  ]
}}

Keep it factual. If unknown, use empty strings or empty arrays.
No markdown, no explanation — ONLY the JSON object.
"""


class CompanyResearchAgent:
    """
    Gathers company intelligence to personalize job applications.

    Uses Claude Haiku (fast + cheap) to extract and synthesize company
    context from the job description text.
    """

    def __init__(self):
        self._client: Optional[anthropic.AsyncAnthropic] = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._client

    async def research(self, job: dict) -> dict:
        """
        Research a company for a job application.

        Returns a dict with company intelligence fields.
        """
        prompt = _PROMPT.format(
            company=job.get("company", "Unknown"),
            title=job.get("title", "Unknown"),
            source=job.get("source", "unknown"),
            description=(job.get("description") or "")[:3000],
        )

        try:
            client = self._get_client()
            msg = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)

        except Exception as e:
            logger.warning(f"CompanyResearchAgent error for {job.get('company')}: {e}")
            return {
                "industry": "Unknown",
                "size": "Unknown",
                "growth_stage": "Unknown",
                "tech_stack": [],
                "culture": "Professional work environment.",
                "remote_policy": "unknown",
                "recent_news": "",
                "talking_points": [],
            }
