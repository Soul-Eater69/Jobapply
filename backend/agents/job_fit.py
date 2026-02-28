"""
Job Fit Scoring Agent.

Uses GPT to evaluate whether a job posting is worth applying to.
Returns a fit score (0-100), verdict, and reasoning — replacing the
"Human QA layer" with an AI decision layer.
"""

import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from ..config import settings, load_user_profile

logger = logging.getLogger(__name__)

_PROMPT = """\
You are an expert career coach and senior technical recruiter evaluating job-candidate fit.

## Candidate Profile
{profile_summary}

## Job Posting
Title:    {title}
Company:  {company}
Location: {location}
Salary:   {salary}

Description:
{description}

## Task
Evaluate fit between the candidate and this job. Assess:
1. Skill alignment (required vs candidate skills)
2. Experience level match (over/under-qualified?)
3. Career trajectory fit (does this role make sense for them?)
4. Compensation alignment (if salary info available)
5. Job posting quality (spam, unrealistic requirements, red flags?)

Return ONLY a JSON object (no markdown, no explanation):
{{
  "fit_score": <integer 0-100>,
  "verdict": "<apply|skip>",
  "reasoning": "<2-3 sentences explaining the decision>",
  "key_strengths": ["<strength1>", "<strength2>", "<strength3>"],
  "key_gaps": ["<gap1>", "<gap2>"],
  "red_flags": ["<flag1>"]
}}

Scoring guide: 80-100 = strong match, 65-79 = reasonable match (apply),
50-64 = borderline (skip unless desperate), 0-49 = poor fit (skip).
"""


class JobFitAgent:
    """
    Evaluates job-candidate fit using GPT-4o.

    Replaces human QA with an AI decision layer that reads the full JD,
    compares it against the candidate profile, and returns a structured
    fit verdict — preventing wasted time on low-fit applications.
    """

    def __init__(self):
        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    async def evaluate(self, job: dict) -> dict:
        """
        Evaluate job fit for the current user profile.

        Returns:
            fit_score (int 0-100)
            verdict   ("apply" | "skip")
            fit_reasoning (str)
            key_strengths (list[str])
            key_gaps      (list[str])
            red_flags     (list[str])
        """
        profile = load_user_profile()
        prompt = _PROMPT.format(
            profile_summary=_format_profile(profile),
            title=job.get("title", "Unknown"),
            company=job.get("company", "Unknown"),
            location=job.get("location", "Unknown"),
            salary=job.get("salary") or "Not specified",
            description=(job.get("description") or "")[:4000],
        )

        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                max_tokens=700,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "You are a job fit evaluator. Respond only with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
            )
            data = json.loads(response.choices[0].message.content.strip())
            return {
                "fit_score": int(data.get("fit_score", 65)),
                "verdict": data.get("verdict", "apply"),
                "fit_reasoning": data.get("reasoning", ""),
                "key_strengths": data.get("key_strengths", []),
                "key_gaps": data.get("key_gaps", []),
                "red_flags": data.get("red_flags", []),
            }

        except Exception as e:
            logger.warning(f"JobFitAgent error for {job.get('title')}: {e}")
            # Fail open: allow the job to proceed
            return {
                "fit_score": 70,
                "verdict": "apply",
                "fit_reasoning": "AI evaluation unavailable — proceeding with default approval.",
                "key_strengths": [],
                "key_gaps": [],
                "red_flags": [],
            }


def _format_profile(profile: dict) -> str:
    name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
    experience = profile.get("experience", [])

    lines = [
        f"Name: {name}",
        f"Current Role: {profile.get('current_role', 'Not specified')}",
        f"Years of Experience: {profile.get('years_experience', 'Not specified')}",
        f"Summary: {(profile.get('summary') or '')[:500]}",
        f"Skills: {', '.join(profile.get('skills', [])[:40])}",
        f"Desired Salary: {profile.get('desired_salary', 'Not specified')}",
        f"Work Authorization: {profile.get('work_authorization', 'Not specified')}",
    ]

    if experience:
        lines.append("Recent Experience:")
        for exp in experience[:3]:
            lines.append(
                f"  - {exp.get('title')} at {exp.get('company')} ({exp.get('duration', '')})"
            )

    return "\n".join(lines)
