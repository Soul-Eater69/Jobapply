"""
Follow-Up Agent.

Monitors applied jobs that haven't received a recruiter response after
a configurable number of days, and generates structured follow-up email
drafts. Enables "intentional follow-ups" vs letting apps disappear.
"""

import logging
from datetime import datetime, timedelta
from typing import List

from openai import AsyncOpenAI

from ..config import settings, load_user_profile

logger = logging.getLogger(__name__)

_PROMPT = """\
You are a professional job seeker writing a follow-up email after submitting a job application.

Candidate:   {name}
Applied For: {title} at {company}
Applied On:  {applied_date}
Days Since:  {days_since}

Write a brief, professional follow-up email (4-6 sentences, under 130 words):
1. Open with a specific reference to the role (not "I applied recently")
2. Reiterate one concrete, metrics-driven reason you're a strong fit
3. Acknowledge their busy schedule, express continued interest
4. Politely request an update on timeline
5. Close confidently — not apologetically

Output format (plain text, no markdown):
Subject: <compelling subject line>

<email body>

<sign-off>
{name}
"""


class FollowUpAgent:
    """
    Generates follow-up email drafts and tracks which applications
    have been followed up on.
    """

    def __init__(self):
        self._client = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    async def get_pending_followups(
        self,
        db,
        follow_up_after_days: int = 7,
    ) -> List[dict]:
        """
        Find applications that need follow-up and generate email drafts.

        Returns list of dicts: {db_id, job_id, title, company, applied_at, email_draft}
        """
        from ..models import JobApplication

        cutoff = datetime.utcnow() - timedelta(days=follow_up_after_days)
        pending = (
            db.query(JobApplication)
            .filter(
                JobApplication.status == "applied",
                JobApplication.applied_at <= cutoff,
                JobApplication.followup_sent_at.is_(None),
                JobApplication.recruiter_replied_at.is_(None),
            )
            .all()
        )

        results = []
        for app in pending:
            try:
                draft = await self._generate(app)
                results.append({
                    "db_id": app.id,
                    "job_id": app.job_id,
                    "title": app.title,
                    "company": app.company,
                    "applied_at": app.applied_at.isoformat() if app.applied_at else None,
                    "days_since": (datetime.utcnow() - app.applied_at).days if app.applied_at else 0,
                    "email_draft": draft,
                })
            except Exception as e:
                logger.warning(f"FollowUpAgent error for app {app.id}: {e}")

        return results

    async def mark_sent(self, db, db_id: int) -> bool:
        """Mark a follow-up as sent. Returns True on success."""
        from ..models import JobApplication

        app = db.query(JobApplication).filter(JobApplication.id == db_id).first()
        if not app:
            return False
        app.followup_sent_at = datetime.utcnow()
        db.commit()
        return True

    async def mark_replied(self, db, db_id: int) -> bool:
        """Mark that the recruiter replied. Returns True on success."""
        from ..models import JobApplication

        app = db.query(JobApplication).filter(JobApplication.id == db_id).first()
        if not app:
            return False
        app.recruiter_replied_at = datetime.utcnow()
        db.commit()
        return True

    async def _generate(self, app) -> str:
        profile = load_user_profile()
        name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        days_since = (datetime.utcnow() - app.applied_at).days if app.applied_at else 7

        prompt = _PROMPT.format(
            name=name or "the applicant",
            title=app.title,
            company=app.company,
            applied_date=(
                app.applied_at.strftime("%B %d, %Y") if app.applied_at else "recently"
            ),
            days_since=days_since,
        )

        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=350,
                messages=[
                    {"role": "system", "content": "You write professional, concise follow-up emails. Plain text only."},
                    {"role": "user", "content": prompt},
                ],
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Follow-up generation error: {e}")
            return (
                f"Subject: Follow-up: {app.title} Application\n\n"
                f"Dear Hiring Manager,\n\n"
                f"I wanted to follow up on my application for the {app.title} role at "
                f"{app.company}, submitted {days_since} days ago. I remain very interested "
                f"in this opportunity and would love to learn about next steps.\n\n"
                f"Please let me know if you need any additional information.\n\n"
                f"Best regards,\n{name}"
            )
