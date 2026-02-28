"""
Cover Letter Generation Agent.

Generates ATS-optimized, role-specific cover letters tailored to each job
using Claude. Replaces the old Human QA layer with AI quality assurance.
"""

import logging
from pathlib import Path
from typing import Optional

import anthropic

from ..config import settings, load_user_profile, BASE_DIR

logger = logging.getLogger(__name__)

COVER_LETTERS_DIR = BASE_DIR / "cover_letters"
COVER_LETTERS_DIR.mkdir(exist_ok=True)

_PROMPT = """\
You are an expert cover letter writer who creates compelling, authentic, ATS-friendly cover letters.

## Candidate Profile
{profile_summary}

## Target Role
Title:   {title}
Company: {company}
Location:{location}

## Job Description
{description}

## Company Intelligence
{company_intel}

## Instructions
Write a professional cover letter (300-420 words, 3-4 paragraphs):

1. **Opening**: Hook that names the specific role + something concrete about the company
   (use company intelligence if available, otherwise JD context)
2. **Value paragraph**: 2-3 specific achievements from the candidate's experience
   with real metrics (%, $, users, ms improvements) that directly match job requirements
3. **Skills + fit paragraph**: Show skill alignment using keywords from the JD naturally.
   Mention their specific tech stack, methodology, or challenge they're solving.
4. **Closing**: Confident call to action. Express excitement, not desperation.

Rules:
- ATS keywords from the JD should appear naturally — never stuffed
- Sound like a real human wrote this, not a template
- Quantify everything possible — vague bullets kill applications
- DO NOT start with "I am writing to" or "I am excited to apply"
- DO NOT use the phrase "I am a passionate [X]"
- Address to "Hiring Manager" unless name is known

Output: Plain text only, no markdown.
Start directly with: Dear Hiring Manager,
"""


class CoverLetterAgent:
    """
    Generates tailored cover letters for each job application using Claude.

    Saves the letter as a .txt file alongside the resume PDF, and returns
    the file path + raw text for storage in the database.
    """

    def __init__(self):
        self._client: Optional[anthropic.AsyncAnthropic] = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._client

    async def generate(self, job: dict, company_research: Optional[dict] = None) -> dict:
        """
        Generate a cover letter for the job.

        Returns:
            cover_letter_content (str) - full text
            cover_letter_path    (str) - saved file path
        """
        profile = load_user_profile()
        profile_summary = _format_profile(profile)

        company_intel = _format_research(company_research)

        prompt = _PROMPT.format(
            profile_summary=profile_summary,
            title=job.get("title", "the role"),
            company=job.get("company", "your company"),
            location=job.get("location") or "Flexible",
            description=(job.get("description") or "")[:3500],
            company_intel=company_intel,
        )

        cover_letter = ""
        try:
            client = self._get_client()
            msg = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )
            cover_letter = msg.content[0].text.strip()

        except Exception as e:
            logger.warning(f"CoverLetterAgent error for {job.get('title')}: {e}")
            cover_letter = _fallback(job, profile)

        # Save to file
        job_id = job.get("job_id", "unknown")
        safe_id = "".join(c for c in str(job_id) if c.isalnum() or c in "-_")[:40]
        path = COVER_LETTERS_DIR / f"cover_{safe_id}.txt"
        path.write_text(cover_letter, encoding="utf-8")

        return {
            "cover_letter_content": cover_letter,
            "cover_letter_path": str(path),
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_profile(profile: dict) -> str:
    personal = profile.get("Personal", {})
    prof = profile.get("Professional", {})
    skills = profile.get("Skills", [])
    experience = profile.get("Experience", [])

    lines = [
        f"Name: {personal.get('first_name', '')} {personal.get('last_name', '')}",
        f"Email: {personal.get('email', '')}",
        f"Current Role: {prof.get('current_role', '')}",
        f"Years of Experience: {prof.get('years_experience', '')}",
        f"Summary: {(prof.get('summary') or '')[:600]}",
        f"Skills: {', '.join(skills[:30])}",
    ]

    if experience:
        lines.append("Experience:")
        for exp in experience[:3]:
            highlights = " | ".join((exp.get("highlights") or [])[:2])
            lines.append(
                f"  {exp.get('title')} @ {exp.get('company')} ({exp.get('duration', '')})"
                + (f": {highlights}" if highlights else "")
            )

    return "\n".join(lines)


def _format_research(research: Optional[dict]) -> str:
    if not research:
        return "No company research available."
    parts = [
        f"Industry: {research.get('industry', 'Unknown')}",
        f"Size: {research.get('size', 'Unknown')}",
        f"Stage: {research.get('growth_stage', 'Unknown')}",
        f"Remote Policy: {research.get('remote_policy', 'Unknown')}",
        f"Tech Stack: {', '.join(research.get('tech_stack', []))}",
        f"Culture: {research.get('culture', '')}",
        f"Recent News: {research.get('recent_news', '')}",
    ]
    if research.get("talking_points"):
        parts.append("Key Talking Points:")
        for tp in research["talking_points"]:
            parts.append(f"  - {tp}")
    return "\n".join(parts)


def _fallback(job: dict, profile: dict) -> str:
    personal = profile.get("Personal", {})
    prof = profile.get("Professional", {})
    name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
    role = prof.get("current_role", "a software professional")
    years = prof.get("years_experience", "several")

    return (
        f"Dear Hiring Manager,\n\n"
        f"I am writing to express my strong interest in the {job.get('title')} position "
        f"at {job.get('company')}. As {role} with {years} years of experience, "
        f"I believe my background aligns well with your requirements.\n\n"
        f"Throughout my career I have built a track record of delivering results "
        f"through technical excellence and cross-functional collaboration. I am excited "
        f"about the opportunity to bring this experience to your team.\n\n"
        f"I would welcome the chance to discuss how I can contribute to "
        f"{job.get('company')}'s continued success.\n\n"
        f"Best regards,\n{name}"
    )
