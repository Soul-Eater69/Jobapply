from sqlalchemy import Column, Integer, String, DateTime, Text, Float, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class JobApplication(Base):
    __tablename__ = "job_applications"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, unique=True, index=True)           # External job ID
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String)
    salary = Column(String)
    job_type = Column(String)                                   # full-time, part-time, contract
    remote = Column(Boolean, default=False)
    source = Column(String, nullable=False)                    # linkedin, indeed, glassdoor, dice
    job_url = Column(String, nullable=False)
    apply_url = Column(String)
    description = Column(Text)
    posted_at = Column(DateTime)                               # When job was posted
    scraped_at = Column(DateTime, default=datetime.utcnow)    # When we found it
    applied_at = Column(DateTime)                              # When we applied
    status = Column(String, default="pending")                 # pending, applied, failed, skipped
    failure_reason = Column(String)
    resume_path = Column(String)                               # Path to tailored resume PDF
    resume_content = Column(Text)                              # Resume text used
    matched_skills = Column(JSON)                              # Skills matched from JD
    required_skills = Column(JSON)                             # Skills required by JD
    ats_score = Column(Float)                                  # ATS match score
    notes = Column(Text)
    error_log = Column(Text)

    # ── Agent Layer Fields ────────────────────────────────────────────────────
    fit_score = Column(Float)                          # Agent job-fit score 0-100
    fit_reasoning = Column(Text)                       # Agent reasoning text
    company_research = Column(JSON)                    # Company intelligence dict
    cover_letter_path = Column(String)                 # Path to cover letter .txt
    cover_letter_content = Column(Text)                # Cover letter text (stored)
    followup_sent_at = Column(DateTime)                # When follow-up email was sent
    recruiter_replied_at = Column(DateTime)            # When recruiter responded
    outcome = Column(String, default="pending")        # pending|interview|rejected|offer


class UserConfig(Base):
    __tablename__ = "user_config"

    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
