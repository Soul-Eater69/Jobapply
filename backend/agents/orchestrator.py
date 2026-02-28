"""
Agent Orchestrator.

Coordinates the full AI decision pipeline for every scraped job before
it enters the resume/apply workers. This is the "AI agent layer" that
replaces the Human QA layer.

Pipeline per job:
  1. JobFitAgent        → score fit (0-100), skip if below threshold
  2. CompanyResearchAgent → gather company context
  3. CoverLetterAgent   → generate tailored cover letter
  4. Return enriched job → handed to ResumeWorker → ApplyWorker

Each step enriches the job dict with new fields that flow downstream.
"""

import logging
from typing import Callable, Optional

from .job_fit import JobFitAgent
from .company_research import CompanyResearchAgent
from .cover_letter import CoverLetterAgent

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Runs the full AI agent pipeline for a single scraped job.

    Returns the enriched job dict if approved, or None if skipped.
    Downstream workers (resume, apply) receive the enriched dict and
    have access to: fit_score, fit_reasoning, company_research,
    cover_letter_content, cover_letter_path.
    """

    def __init__(self, min_fit_score: int = 65):
        self.min_fit_score = min_fit_score
        self._job_fit = JobFitAgent()
        self._company_research = CompanyResearchAgent()
        self._cover_letter = CoverLetterAgent()

    async def process(
        self,
        job: dict,
        broadcast: Optional[Callable] = None,
    ) -> Optional[dict]:
        """
        Run the full agent pipeline for one job.

        Args:
            job:       Scraped job dict from the scraper.
            broadcast: Optional async callable for WebSocket log messages.

        Returns:
            Enriched job dict if approved, None if skipped.
        """
        title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")

        async def _log(msg: str, level: str = "info"):
            logger.info(msg)
            if broadcast:
                await broadcast({"type": "log", "data": {"message": msg, "level": level}})

        # ── Step 1: Job Fit Evaluation ────────────────────────────────────────
        await _log(f"[Agent] Evaluating fit: {title} @ {company}")
        fit = await self._job_fit.evaluate(job)
        job.update(fit)

        fit_score = fit.get("fit_score", 0)
        verdict = fit.get("verdict", "skip")
        reasoning = fit.get("fit_reasoning", "")

        if verdict == "skip" or fit_score < self.min_fit_score:
            await _log(
                f"[Agent] Skipped {title} @ {company} "
                f"(fit {fit_score}/100) — {reasoning}",
                "warning",
            )
            return None

        await _log(
            f"[Agent] Approved {title} @ {company} (fit {fit_score}/100)",
            "success",
        )

        # ── Step 2: Company Research ──────────────────────────────────────────
        await _log(f"[Agent] Researching {company}...")
        research = await self._company_research.research(job)
        job["company_research"] = research

        # ── Step 3: Cover Letter Generation ──────────────────────────────────
        await _log(f"[Agent] Writing cover letter for {title} @ {company}...")
        cover = await self._cover_letter.generate(job, company_research=research)
        job.update(cover)

        await _log(
            f"[Agent] Pipeline complete: {title} @ {company} → resume + apply",
            "success",
        )
        return job

    async def process_batch(
        self,
        jobs: list,
        broadcast: Optional[Callable] = None,
    ) -> list:
        """
        Process a batch of jobs through the agent pipeline.

        Returns list of approved + enriched jobs.
        """
        import asyncio

        results = []
        for job in jobs:
            try:
                enriched = await self.process(job, broadcast=broadcast)
                if enriched is not None:
                    results.append(enriched)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(
                    f"Orchestrator error for {job.get('title')} @ {job.get('company')}: {e}",
                    exc_info=True,
                )
        return results
