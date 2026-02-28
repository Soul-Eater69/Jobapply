"""
Automation scheduler.
Orchestrates scrapers → priority queue → resume workers → apply workers.
"""
import asyncio
import logging
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from .schemas import AutomationConfig
from .models import JobApplication
from .queue_manager import JobQueueManager
from .database import SessionLocal

logger = logging.getLogger(__name__)

# Global queue instance
_queue: JobQueueManager = None


async def run_automation_loop(
    config: AutomationConfig,
    db: Session,
    state: dict,
    broadcast: Callable,
):
    global _queue

    from .scraper.linkedin import LinkedInScraper
    from .scraper.indeed import IndeedScraper
    from .scraper.glassdoor import GlassdoorScraper
    from .scraper.dice import DiceScraper
    from .scraper.remotive import RemotiveScraper
    from .scraper.weworkremotely import WeWorkRemotelyScraper
    from .scraper.ziprecruiter import ZipRecruiterScraper
    from .scraper.greenhouse import GreenhouseScraper

    SCRAPER_REGISTRY = {
        "linkedin": LinkedInScraper,
        "indeed": IndeedScraper,
        "glassdoor": GlassdoorScraper,
        "dice": DiceScraper,
        "remotive": RemotiveScraper,
        "weworkremotely": WeWorkRemotelyScraper,
        "ziprecruiter": ZipRecruiterScraper,
        "greenhouse": GreenhouseScraper,
    }

    # Initialize queue with workers
    _queue = JobQueueManager(max_apply_workers=2, max_resume_workers=3)
    await _queue.start(config, SessionLocal, broadcast)

    try:
        while state["running"]:
            state["last_check"] = datetime.utcnow()
            state["current_action"] = "Scanning job boards..."
            await broadcast({"type": "status", "data": {
                "current_action": state["current_action"],
                "running": True,
            }})

            all_jobs = []

            # ── Scrape all enabled sources ────────────────────────────────
            for source in config.sources:
                scraper_cls = SCRAPER_REGISTRY.get(source)
                if not scraper_cls:
                    continue

                state["current_action"] = f"Scraping {source}..."
                await broadcast({"type": "log", "data": {
                    "message": f"Scanning {source.title()}...",
                    "level": "info",
                }})

                try:
                    scraper = scraper_cls()
                    jobs = await scraper.search_jobs(
                        keywords=config.search_keywords,
                        locations=config.locations,
                        max_age_hours=1,
                        remote_only=config.remote_only,
                        job_types=config.job_types,
                        experience_levels=config.experience_level,
                        target_companies=config.target_companies,
                    )
                    await scraper.close()

                    # Company filters
                    if config.target_companies:
                        jobs = [j for j in jobs if any(
                            c.lower() in j.get("company", "").lower()
                            for c in config.target_companies
                        )]

                    if config.blocked_companies:
                        jobs = [j for j in jobs if not any(
                            c.lower() in j.get("company", "").lower()
                            for c in config.blocked_companies
                        )]

                    all_jobs.extend(jobs)
                    state["jobs_found"] += len(jobs)

                    await broadcast({"type": "log", "data": {
                        "message": f"{source.title()}: found {len(jobs)} fresh jobs",
                        "level": "success" if jobs else "info",
                    }})

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Scraper error [{source}]: {e}", exc_info=True)
                    await broadcast({"type": "log", "data": {
                        "message": f"Scraper error [{source}]: {str(e)[:120]}",
                        "level": "error",
                    }})

            # ── Deduplicate against DB ────────────────────────────────────
            new_jobs = []
            db_session = SessionLocal()
            try:
                for job in all_jobs:
                    exists = db_session.query(JobApplication).filter(
                        JobApplication.job_id == job.get("job_id")
                    ).first()
                    if not exists:
                        new_jobs.append(job)
            finally:
                db_session.close()

            await broadcast({"type": "log", "data": {
                "message": f"New unique jobs this scan: {len(new_jobs)}",
                "level": "info",
            }})

            # ── Push to priority queue ────────────────────────────────────
            if new_jobs:
                _queue.push_jobs(new_jobs)
                queue_stats = _queue.get_stats()
                await broadcast({"type": "queue_stats", "data": queue_stats})

            # ── Sync state from queue ─────────────────────────────────────
            qs = _queue.get_stats()
            state["jobs_applied"] = qs["applied"]
            state["jobs_failed"] = qs["failed"]

            await broadcast({"type": "status", "data": {
                "running": state["running"],
                "jobs_found": state["jobs_found"],
                "jobs_applied": state["jobs_applied"],
                "jobs_failed": state["jobs_failed"],
                "queue_size": qs["queue_size"],
                "current_action": f"Waiting {config.check_interval_minutes}min before next scan...",
                "last_check": state["last_check"].isoformat() if state["last_check"] else None,
            }})

            # ── Wait for next scan cycle ──────────────────────────────────
            await asyncio.sleep(config.check_interval_minutes * 60)

    except asyncio.CancelledError:
        logger.info("Automation loop cancelled")
        raise
    finally:
        if _queue:
            await _queue.stop()
        state["running"] = False
        state["current_action"] = "idle"


async def save_job(db: Session, job: dict, status: str, failure_reason: str = None):
    now = datetime.utcnow()
    record = JobApplication(
        job_id=job.get("job_id", f"manual_{now.timestamp()}"),
        title=job.get("title", "Unknown"),
        company=job.get("company", "Unknown"),
        location=job.get("location"),
        salary=job.get("salary"),
        job_type=job.get("job_type"),
        remote=job.get("remote", False),
        source=job.get("source", "unknown"),
        job_url=job.get("job_url", ""),
        apply_url=job.get("apply_url"),
        description=(job.get("description", "") or "")[:10000],
        posted_at=job.get("posted_at"),
        scraped_at=now,
        applied_at=now if status == "applied" else None,
        status=status,
        failure_reason=failure_reason,
        resume_path=job.get("resume_path"),
        resume_content=(job.get("resume_content") or "")[:5000],
        matched_skills=job.get("matched_skills"),
        required_skills=job.get("required_skills"),
        ats_score=job.get("ats_score"),
        # Agent fields
        fit_score=job.get("fit_score"),
        fit_reasoning=(job.get("fit_reasoning") or "")[:1000],
        company_research=job.get("company_research"),
        cover_letter_path=job.get("cover_letter_path"),
        cover_letter_content=(job.get("cover_letter_content") or "")[:8000],
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
