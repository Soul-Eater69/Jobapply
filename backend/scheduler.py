"""
Automation scheduler.

Orchestrates a tiered, proactive sourcing pipeline:

  Tier 1 — ATS Direct (Lever, Ashby, Greenhouse, Remotive, Dice, ZipRecruiter)
            Jobs appear here before LinkedIn aggregates them (2-24h advantage).

  Tier 2 — Company Watchlist
            Monitor user-specified target companies across ALL ATS platforms.

  Tier 3 — Aggregators (LinkedIn, Indeed, Glassdoor)
            High competition, wide coverage. Run every other scan cycle.

  Tier 4 — Hiring Signals + Direct Outreach (session startup only)
            Detect companies showing hiring signals before a role is posted.

All scraped jobs flow: Scraper → AI Agent Pipeline → Resume → Apply
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

# ── Scraper Registry ──────────────────────────────────────────────────────────

TIER1_SOURCES = {
    # ATS-direct: jobs appear hours before LinkedIn/Indeed
    "greenhouse":     "scraper.greenhouse.GreenhouseScraper",
    "lever":          "scraper.lever.LeverScraper",
    "ashby":          "scraper.ashby.AshbyScraper",
    "remotive":       "scraper.remotive.RemotiveScraper",
    "weworkremotely": "scraper.weworkremotely.WeWorkRemotelyScraper",
    "dice":           "scraper.dice.DiceScraper",
    "ziprecruiter":   "scraper.ziprecruiter.ZipRecruiterScraper",
}

TIER2_SOURCES = {
    "watchlist": "scraper.company_watchlist.CompanyWatchlistScraper",
}

TIER3_SOURCES = {
    "linkedin":  "scraper.linkedin.LinkedInScraper",
    "indeed":    "scraper.indeed.IndeedScraper",
    "glassdoor": "scraper.glassdoor.GlassdoorScraper",
}

ALL_SOURCES = {**TIER1_SOURCES, **TIER2_SOURCES, **TIER3_SOURCES}


def _load_scraper(dotted_path: str):
    """Lazily import a scraper class from a dotted module path."""
    from importlib import import_module
    module_path, cls_name = dotted_path.rsplit(".", 1)
    module = import_module(f".{module_path}", package=__package__)
    return getattr(module, cls_name)


async def run_automation_loop(
    config: AutomationConfig,
    db: Session,
    state: dict,
    broadcast: Callable,
):
    global _queue

    # Initialize queue with agent + resume + apply workers
    _queue = JobQueueManager(max_apply_workers=2, max_resume_workers=3, max_agent_workers=2)
    await _queue.start(config, SessionLocal, broadcast)

    # ── Tier 4: Hiring signal detection (once at session start) ───────────
    if config.target_companies and getattr(config, "enable_signals", True):
        asyncio.create_task(
            _run_signal_detection(config, broadcast),
            name="signal-detector",
        )

    scan_count = 0

    try:
        while state["running"]:
            scan_count += 1
            state["last_check"] = datetime.utcnow()
            state["current_action"] = "Scanning job boards..."
            await broadcast({"type": "status", "data": {
                "current_action": state["current_action"],
                "running": True,
            }})

            enabled = set(config.sources)
            all_jobs = []

            # ── Tier 1: ATS-direct ────────────────────────────────────────
            tier1 = [s for s in enabled if s in TIER1_SOURCES]
            if tier1:
                jobs = await _scrape_sources(
                    tier1, TIER1_SOURCES, config,
                    max_age_hours=2, state=state, broadcast=broadcast,
                )
                all_jobs.extend(jobs)

            # ── Tier 2: Company watchlist ─────────────────────────────────
            if "watchlist" in enabled and config.target_companies:
                await broadcast({"type": "log", "data": {
                    "message": f"Watching {len(config.target_companies)} target companies...",
                    "level": "info",
                }})
                jobs = await _scrape_sources(
                    ["watchlist"], TIER2_SOURCES, config,
                    max_age_hours=3, state=state, broadcast=broadcast,
                )
                all_jobs.extend(jobs)

            # ── Tier 3: Aggregators (every other cycle) ───────────────────
            if scan_count % 2 == 0:
                tier3 = [s for s in enabled if s in TIER3_SOURCES]
                if tier3:
                    jobs = await _scrape_sources(
                        tier3, TIER3_SOURCES, config,
                        max_age_hours=1, state=state, broadcast=broadcast,
                    )
                    all_jobs.extend(jobs)

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
                "message": (
                    f"New unique jobs this scan: {len(new_jobs)} "
                    f"(total scraped: {len(all_jobs)})"
                ),
                "level": "info",
            }})

            # ── Push to priority queue → AI agent pipeline ────────────────
            if new_jobs:
                _queue.push_jobs(new_jobs)
                await broadcast({"type": "queue_stats", "data": _queue.get_stats()})

            # ── Sync state ────────────────────────────────────────────────
            qs = _queue.get_stats()
            state["jobs_applied"] = qs["applied"]
            state["jobs_failed"] = qs["failed"]

            await broadcast({"type": "status", "data": {
                "running": state["running"],
                "jobs_found": state["jobs_found"],
                "jobs_applied": state["jobs_applied"],
                "jobs_failed": state["jobs_failed"],
                "queue_size": qs["queue_size"],
                "agent_approved": qs.get("agent_approved", 0),
                "agent_skipped": qs.get("agent_skipped", 0),
                "current_action": (
                    f"Next scan in {config.check_interval_minutes}min..."
                ),
                "last_check": (
                    state["last_check"].isoformat() if state["last_check"] else None
                ),
            }})

            await asyncio.sleep(config.check_interval_minutes * 60)

    except asyncio.CancelledError:
        logger.info("Automation loop cancelled")
        raise
    finally:
        if _queue:
            await _queue.stop()
        state["running"] = False
        state["current_action"] = "idle"


async def _scrape_sources(
    sources: list,
    registry: dict,
    config: AutomationConfig,
    max_age_hours: int,
    state: dict,
    broadcast: Callable,
) -> list:
    """Run a list of scrapers and return all jobs collected."""
    all_jobs = []
    for source in sources:
        dotted = registry.get(source)
        if not dotted:
            continue
        state["current_action"] = f"Scanning {source}..."
        await broadcast({"type": "log", "data": {
            "message": f"Scanning {source.title()}...",
            "level": "info",
        }})
        try:
            cls = _load_scraper(dotted)
            scraper = cls()
            jobs = await scraper.search_jobs(
                keywords=config.search_keywords,
                locations=config.locations,
                max_age_hours=max_age_hours,
                remote_only=config.remote_only,
                job_types=config.job_types,
                experience_levels=config.experience_level,
                target_companies=config.target_companies,
            )
            await scraper.close()

            # Blocked company filter
            if config.blocked_companies:
                jobs = [
                    j for j in jobs
                    if not any(
                        c.lower() in j.get("company", "").lower()
                        for c in config.blocked_companies
                    )
                ]

            all_jobs.extend(jobs)
            state["jobs_found"] = state.get("jobs_found", 0) + len(jobs)

            await broadcast({"type": "log", "data": {
                "message": f"{source.title()}: {len(jobs)} fresh jobs",
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

    return all_jobs


async def _run_signal_detection(config: AutomationConfig, broadcast: Callable):
    """Run hiring signal detection once at session start."""
    try:
        from .agents.signal_detector import HiringSignalDetector
        detector = HiringSignalDetector()

        companies = (config.target_companies or [])[:30]
        if not companies:
            return

        await broadcast({"type": "log", "data": {
            "message": f"[Signals] Analyzing {len(companies)} companies for hiring signals...",
            "level": "info",
        }})

        signals = await detector.detect(
            companies=companies,
            keywords=config.search_keywords,
            experience_level=(config.experience_level or [None])[0],
        )

        if signals:
            await broadcast({"type": "signals", "data": {
                "signals": detector.format_for_broadcast(signals),
                "count": len(signals),
            }})
            await broadcast({"type": "log", "data": {
                "message": f"[Signals] {len(signals)} companies showing hiring signals",
                "level": "success",
            }})
        else:
            await broadcast({"type": "log", "data": {
                "message": "[Signals] No strong signals detected for target companies",
                "level": "info",
            }})

    except Exception as e:
        logger.warning(f"Signal detection error: {e}")


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
