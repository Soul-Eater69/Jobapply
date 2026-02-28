from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class JobApplicationOut(BaseModel):
    id: int
    job_id: str
    title: str
    company: str
    location: Optional[str]
    salary: Optional[str]
    job_type: Optional[str]
    remote: bool
    source: str
    job_url: str
    apply_url: Optional[str]
    description: Optional[str]
    posted_at: Optional[datetime]
    scraped_at: datetime
    applied_at: Optional[datetime]
    status: str
    failure_reason: Optional[str]
    resume_path: Optional[str]
    matched_skills: Optional[Any]
    required_skills: Optional[Any]
    ats_score: Optional[float]
    notes: Optional[str]
    # Agent fields
    fit_score: Optional[float] = None
    fit_reasoning: Optional[str] = None
    cover_letter_path: Optional[str] = None
    followup_sent_at: Optional[datetime] = None
    recruiter_replied_at: Optional[datetime] = None
    outcome: Optional[str] = None

    class Config:
        from_attributes = True


class JobStats(BaseModel):
    total: int
    applied: int
    failed: int
    pending: int
    skipped: int
    today: int
    this_week: int
    avg_ats_score: Optional[float]
    avg_fit_score: Optional[float] = None
    top_companies: List[dict]
    by_source: List[dict]
    by_status: List[dict]
    # Tracking stats
    pending_followups: int = 0
    interviews: int = 0
    offers: int = 0


class AutomationConfig(BaseModel):
    search_keywords: List[str]
    locations: List[str]
    target_companies: Optional[List[str]] = None
    blocked_companies: Optional[List[str]] = None
    job_types: Optional[List[str]] = None
    max_applications_per_run: int = 20
    max_applications_per_day: int = 50
    # Tier 1 (ATS-direct) + Tier 2 (watchlist) + Tier 3 (aggregators)
    sources: List[str] = [
        # Tier 1: ATS-direct (2-24h before LinkedIn)
        "greenhouse", "lever", "ashby", "remotive", "weworkremotely", "dice", "ziprecruiter",
        # Tier 2: Company watchlist (checks all ATS for target_companies)
        "watchlist",
        # Tier 3: Aggregators (high competition, run every other cycle)
        "linkedin", "indeed", "glassdoor",
    ]
    check_interval_minutes: int = 15             # 15min default (was 30min)
    min_ats_score: float = 60.0
    min_fit_score: float = 65.0                  # Agent fit threshold (0-100)
    auto_apply: bool = True
    remote_only: bool = False
    salary_min: Optional[int] = None
    experience_level: Optional[List[str]] = None  # entry, mid, senior
    enable_cover_letter: bool = True              # Generate cover letter per job
    enable_signals: bool = True                   # Hiring signal detection at startup
    followup_after_days: int = 7                  # Days before follow-up email


class RunStatus(BaseModel):
    running: bool
    jobs_found_session: int
    jobs_applied_session: int
    jobs_failed_session: int
    current_action: str
    started_at: Optional[datetime]
    last_check: Optional[datetime]


# ── Agent-specific schemas ────────────────────────────────────────────────────

class FollowUpItem(BaseModel):
    db_id: int
    job_id: str
    title: str
    company: str
    applied_at: Optional[str]
    days_since: int
    email_draft: str


class OutcomeUpdate(BaseModel):
    outcome: str   # pending | interview | rejected | offer
    notes: Optional[str] = None


class AgentPipelineStats(BaseModel):
    total_evaluated: int
    approved: int
    skipped: int
    avg_fit_score: Optional[float]
    cover_letters_generated: int
    followups_pending: int
    followups_sent: int
    recruiter_replies: int
    interviews: int
    offers: int
