"""
Direct Outreach Agent.

Generates personalized cold outreach messages to hiring managers at target
companies — for roles that don't yet exist publicly. This is "Tier 4" in the
proactive sourcing strategy, bypassing job postings entirely.

Research shows:
  - Referrals = 7% of applicants, 30-50% of hires
  - Direct outreach response rate: 33-80% (vs 4-10% for cold applications)
  - Outreach timed to hiring signals gets 2-3x normal response rates

Two outreach modes:
  1. signal_outreach — triggered by a detected hiring signal (funding, etc.)
  2. speculative_outreach — proactive inquiry for companies on watchlist
"""

import logging
from typing import Optional

import anthropic

from ..config import settings, load_user_profile

logger = logging.getLogger(__name__)

_SIGNAL_OUTREACH_PROMPT = """\
You are a senior professional writing a highly targeted cold outreach message
to a hiring manager at a company that just showed a significant hiring signal
(e.g., raised funding, launched a product, hired a new executive).

## About You (the sender)
{profile_summary}

## Target Company
Company: {company}
Hiring Signal: {signal_summary}
Signal Type: {signal_type}
Your Best Fit Role: {predicted_role}

## Instructions
Write a SHORT LinkedIn message or email (5-7 sentences, under 100 words):

1. Open by referencing the SPECIFIC hiring signal (don't be vague)
2. Make ONE concrete connection between your skills and what they need RIGHT NOW
3. Include ONE quantified achievement that's directly relevant
4. End with a soft ask — not "I want a job" but "would love 15 minutes"
5. Sound like a confident peer, not a desperate applicant

Tone: Direct, warm, specific. No corporate-speak. No "I am very excited."
No "I am writing to inquire." No buzzwords.

Output two versions:
1. LinkedIn message (under 300 characters for connection request note)
2. Email version (subject line + body, under 120 words)

Format:
LINKEDIN:
<message>

EMAIL:
Subject: <subject>
<body>
"""

_SPECULATIVE_PROMPT = """\
You are a senior professional writing a speculative outreach message to explore
potential opportunities at a target company — no specific role posted yet.

## About You (the sender)
{profile_summary}

## Target Company
Company: {company}
Department/Team: {department}
Why This Company: {why_company}

## Instructions
Write a short, confident outreach message (5-6 sentences, under 90 words).
Reference something SPECIFIC about the company (product, tech stack, mission).
Highlight ONE achievement that would matter to them.
Ask for a conversation — not a job.

Output two versions:

LINKEDIN:
<connection request note, under 300 chars>

EMAIL:
Subject: <subject>
<body>
"""


class OutreachAgent:
    """
    Generates personalized direct outreach messages for hiring managers.

    Used for proactive outreach to companies showing hiring signals or
    to a user's target watchlist companies.
    """

    def __init__(self):
        self._client: Optional[anthropic.AsyncAnthropic] = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._client

    async def generate_signal_outreach(
        self,
        company: str,
        signal: dict,
    ) -> dict:
        """
        Generate outreach triggered by a hiring signal.

        Args:
            company: Company name
            signal:  Dict from HiringSignalDetector.detect()

        Returns:
            {linkedin_message, email_subject, email_body}
        """
        profile = load_user_profile()
        predicted_role = (signal.get("predicted_roles") or ["relevant role"])[0]

        prompt = _SIGNAL_OUTREACH_PROMPT.format(
            profile_summary=_format_profile(profile),
            company=company,
            signal_summary=signal.get("signal_summary", "company growth"),
            signal_type=signal.get("signal_type", "growth"),
            predicted_role=predicted_role,
        )

        return await self._generate(prompt)

    async def generate_speculative_outreach(
        self,
        company: str,
        department: str = "Engineering",
        why_company: str = "",
    ) -> dict:
        """
        Generate speculative outreach for a watchlist company with no signal.

        Returns:
            {linkedin_message, email_subject, email_body}
        """
        profile = load_user_profile()

        prompt = _SPECULATIVE_PROMPT.format(
            profile_summary=_format_profile(profile),
            company=company,
            department=department,
            why_company=why_company or f"interested in {company}'s product and mission",
        )

        return await self._generate(prompt)

    async def _generate(self, prompt: str) -> dict:
        try:
            client = self._get_client()
            msg = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            return _parse_outreach(raw)
        except Exception as e:
            logger.warning(f"Outreach agent error: {e}")
            return {
                "linkedin_message": "",
                "email_subject": "",
                "email_body": "",
                "error": str(e),
            }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_profile(profile: dict) -> str:
    personal = profile.get("Personal", {})
    prof = profile.get("Professional", {})
    skills = profile.get("Skills", [])
    experience = profile.get("Experience", [])

    lines = [
        f"Name: {personal.get('first_name', '')} {personal.get('last_name', '')}",
        f"Current Role: {prof.get('current_role', '')}",
        f"Years Experience: {prof.get('years_experience', '')}",
        f"Top Skills: {', '.join(skills[:15])}",
        f"Summary: {(prof.get('summary') or '')[:400]}",
    ]
    if experience:
        top = experience[0]
        highlights = " | ".join((top.get("highlights") or [])[:2])
        lines.append(f"Most Recent: {top.get('title')} @ {top.get('company')} — {highlights}")

    return "\n".join(lines)


def _parse_outreach(raw: str) -> dict:
    """Parse the two-format output from the LLM."""
    linkedin_msg = ""
    email_subject = ""
    email_body = ""

    try:
        if "LINKEDIN:" in raw:
            li_section = raw.split("LINKEDIN:")[1]
            if "EMAIL:" in li_section:
                linkedin_msg = li_section.split("EMAIL:")[0].strip()
                email_section = li_section.split("EMAIL:")[1].strip()
            else:
                linkedin_msg = li_section.strip()
                email_section = ""
        elif "EMAIL:" in raw:
            email_section = raw.split("EMAIL:")[1].strip()
        else:
            linkedin_msg = raw.strip()
            email_section = ""

        if email_section:
            lines = email_section.strip().split("\n")
            for i, line in enumerate(lines):
                if line.lower().startswith("subject:"):
                    email_subject = line[8:].strip()
                    email_body = "\n".join(lines[i + 1:]).strip()
                    break
            if not email_subject and lines:
                email_subject = lines[0].strip()
                email_body = "\n".join(lines[1:]).strip()

    except Exception as e:
        logger.debug(f"Outreach parse error: {e}")
        linkedin_msg = raw[:300]

    return {
        "linkedin_message": linkedin_msg[:300],   # LinkedIn 300 char limit
        "email_subject": email_subject,
        "email_body": email_body,
    }
