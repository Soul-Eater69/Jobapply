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
    top_companies: List[dict]
    by_source: List[dict]
    by_status: List[dict]


class AutomationConfig(BaseModel):
    search_keywords: List[str]
    locations: List[str]
    target_companies: Optional[List[str]] = None
    blocked_companies: Optional[List[str]] = None
    job_types: Optional[List[str]] = None
    max_applications_per_run: int = 20
    max_applications_per_day: int = 50
    sources: List[str] = ["linkedin", "indeed", "glassdoor", "dice"]
    check_interval_minutes: int = 30
    min_ats_score: float = 60.0
    auto_apply: bool = True
    remote_only: bool = False
    salary_min: Optional[int] = None
    experience_level: Optional[List[str]] = None  # entry, mid, senior


class RunStatus(BaseModel):
    running: bool
    jobs_found_session: int
    jobs_applied_session: int
    jobs_failed_session: int
    current_action: str
    started_at: Optional[datetime]
    last_check: Optional[datetime]
