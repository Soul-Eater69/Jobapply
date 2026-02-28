"""
AI Agent Layer — Agentic decision-making on top of the job pipeline.

Pipeline:
  Scraper → [Agent Orchestrator]
               ├── JobFitAgent        (skip low-fit jobs)
               ├── CompanyResearchAgent (gather context)
               └── CoverLetterAgent   (tailored cover letter)
                         ↓
             ResumeWorker → ApplyWorker → DB
"""

from .orchestrator import AgentOrchestrator
from .job_fit import JobFitAgent
from .cover_letter import CoverLetterAgent
from .company_research import CompanyResearchAgent
from .followup import FollowUpAgent
from .signal_detector import HiringSignalDetector
from .outreach import OutreachAgent

__all__ = [
    "AgentOrchestrator",
    "JobFitAgent",
    "CoverLetterAgent",
    "CompanyResearchAgent",
    "FollowUpAgent",
    "HiringSignalDetector",
    "OutreachAgent",
]
