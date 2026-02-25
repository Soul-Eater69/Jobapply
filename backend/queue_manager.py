"""
Async Job Processing Queue.

Architecture:
  ┌─────────────────────────────────────────────────────────┐
  │  Scrapers  →  job_queue  →  Resume Workers              │
  │                        →  Apply Workers                 │
  │                                                         │
  │  Queues:                                                │
  │    job_queue         (scraped jobs, priority: age)      │
  │    resume_queue      (jobs with resume needed)          │
  │    apply_queue       (jobs ready to apply)              │
  │    dead_letter_queue (failed after max retries)         │
  └─────────────────────────────────────────────────────────┘

Features:
  - Priority queue (newer jobs = higher priority)
  - Per-domain rate limiting (LinkedIn: 1 req/3s, etc.)
  - Retry with exponential backoff
  - Dead letter queue for permanent failures
  - Concurrency control (max N simultaneous applies)
  - Real-time broadcast via WebSocket
"""

import asyncio
import heapq
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Rate Limiter ────────────────────────────────────────────────────────────

class DomainRateLimiter:
    """Per-domain token bucket rate limiter."""

    DEFAULT_LIMITS = {
        "linkedin": 1.0 / 4,    # 1 request per 4s
        "indeed": 1.0 / 3,
        "glassdoor": 1.0 / 5,
        "dice": 1.0 / 2,
        "ziprecruiter": 1.0 / 3,
        "remotive": 1.0 / 1,
        "weworkremotely": 1.0 / 2,
        "greenhouse": 1.0 / 1,
        "default": 1.0 / 2,
    }

    def __init__(self):
        self._tokens: Dict[str, float] = {}
        self._last_refill: Dict[str, float] = {}

    async def acquire(self, domain: str):
        rate = self.DEFAULT_LIMITS.get(domain, self.DEFAULT_LIMITS["default"])
        min_interval = 1.0 / rate

        now = time.monotonic()
        last = self._last_refill.get(domain, 0)
        elapsed = now - last

        if elapsed < min_interval:
            wait = min_interval - elapsed
            logger.debug(f"Rate limiting {domain}: waiting {wait:.2f}s")
            await asyncio.sleep(wait)

        self._last_refill[domain] = time.monotonic()


# ─── Priority Job Item ────────────────────────────────────────────────────────

@dataclass(order=True)
class PriorityJobItem:
    priority: float          # Lower = higher priority (use negative timestamp)
    job: Dict = field(compare=False)
    retries: int = field(default=0, compare=False)
    added_at: float = field(default_factory=time.monotonic, compare=False)


# ─── Queue Manager ────────────────────────────────────────────────────────────

class JobQueueManager:
    def __init__(self, max_apply_workers: int = 2, max_resume_workers: int = 3):
        self._job_heap: List[PriorityJobItem] = []          # Raw scraped jobs
        self._resume_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._apply_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._dead_letter: List[dict] = []

        self.max_apply_workers = max_apply_workers
        self.max_resume_workers = max_resume_workers
        self.rate_limiter = DomainRateLimiter()

        self._running = False
        self._workers: List[asyncio.Task] = []
        self._apply_semaphore = asyncio.Semaphore(max_apply_workers)

        # Callbacks
        self.on_job_processed: Optional[Callable] = None
        self.on_resume_generated: Optional[Callable] = None
        self.on_applied: Optional[Callable] = None
        self.on_failed: Optional[Callable] = None

        # Stats
        self.stats = {
            "queued": 0,
            "resumed_built": 0,
            "applied": 0,
            "failed": 0,
            "dead_letters": 0,
        }

    def push_jobs(self, jobs: List[dict]):
        """Add scraped jobs to the priority queue. Newer jobs = higher priority."""
        for job in jobs:
            # Priority: negative posted_at timestamp (newer = lower number = higher priority)
            posted = job.get("posted_at")
            if isinstance(posted, datetime):
                priority = -posted.timestamp()
            else:
                priority = -time.time()

            item = PriorityJobItem(priority=priority, job=job)
            heapq.heappush(self._job_heap, item)
            self.stats["queued"] += 1

        logger.info(f"Queue: {len(self._job_heap)} jobs pending")

    def pop_job(self) -> Optional[PriorityJobItem]:
        if self._job_heap:
            return heapq.heappop(self._job_heap)
        return None

    @property
    def queue_size(self) -> int:
        return len(self._job_heap)

    async def start(
        self,
        config,
        db_session_factory,
        broadcast: Callable,
    ):
        self._running = True

        # Start resume building workers
        for i in range(self.max_resume_workers):
            task = asyncio.create_task(
                self._resume_worker(f"resume-{i}", config, broadcast),
                name=f"resume-worker-{i}",
            )
            self._workers.append(task)

        # Start apply workers
        for i in range(self.max_apply_workers):
            task = asyncio.create_task(
                self._apply_worker(f"apply-{i}", config, db_session_factory, broadcast),
                name=f"apply-worker-{i}",
            )
            self._workers.append(task)

        # Start job dispatcher
        task = asyncio.create_task(
            self._dispatch_jobs(config),
            name="job-dispatcher",
        )
        self._workers.append(task)

        logger.info(f"Queue started: {self.max_resume_workers} resume workers, {self.max_apply_workers} apply workers")

    async def stop(self):
        self._running = False
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("Queue stopped")

    async def _dispatch_jobs(self, config):
        """Pop jobs from priority queue and dispatch to resume_queue."""
        while self._running:
            item = self.pop_job()
            if item:
                try:
                    source = item.job.get("source", "default")
                    await self.rate_limiter.acquire(source)

                    # Check deduplication limit
                    applied_count = self.stats["applied"]
                    if applied_count >= config.max_applications_per_run:
                        logger.info("Max applications reached, pausing dispatcher")
                        await asyncio.sleep(60)
                        continue

                    await self._resume_queue.put(item)
                except asyncio.QueueFull:
                    # Put back in heap
                    heapq.heappush(self._job_heap, item)
                    await asyncio.sleep(5)
                except asyncio.CancelledError:
                    break
            else:
                await asyncio.sleep(2)

    async def _resume_worker(self, worker_id: str, config, broadcast: Callable):
        """Pull from resume_queue, generate tailored resume, push to apply_queue."""
        from .resume.generator import ResumeGenerator
        generator = ResumeGenerator()

        while self._running:
            try:
                item: PriorityJobItem = await asyncio.wait_for(
                    self._resume_queue.get(), timeout=5.0
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            job = item.job
            try:
                await broadcast({"type": "log", "data": {
                    "message": f"[{worker_id}] Building resume for {job.get('title')} @ {job.get('company')}",
                    "level": "info",
                }})

                result = await generator.generate(job)
                job.update(result)
                self.stats["resumed_built"] += 1

                # ATS threshold check
                ats_score = result.get("ats_score", 0)
                if ats_score < config.min_ats_score:
                    await broadcast({"type": "log", "data": {
                        "message": f"[{worker_id}] ATS score {ats_score:.0f}% too low, skipping",
                        "level": "warning",
                    }})
                    self.stats["failed"] += 1
                    continue

                await broadcast({"type": "log", "data": {
                    "message": f"[{worker_id}] Resume done (ATS: {ats_score:.0f}%) → queuing apply",
                    "level": "success",
                }})

                if config.auto_apply:
                    await self._apply_queue.put(item)

            except Exception as e:
                logger.error(f"[{worker_id}] Resume error: {e}", exc_info=True)
                item.retries += 1
                if item.retries < 3:
                    await asyncio.sleep(2 ** item.retries)
                    await self._resume_queue.put(item)
                else:
                    job["failure_reason"] = f"Resume generation failed after 3 retries: {str(e)[:200]}"
                    self._dead_letter.append(job)
                    self.stats["dead_letters"] += 1

            finally:
                self._resume_queue.task_done()

    async def _apply_worker(self, worker_id: str, config, db_session_factory, broadcast: Callable):
        """Pull from apply_queue, apply to job, save to DB."""
        from .scheduler import save_job

        while self._running:
            try:
                item: PriorityJobItem = await asyncio.wait_for(
                    self._apply_queue.get(), timeout=5.0
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            job = item.job
            async with self._apply_semaphore:
                try:
                    source = job.get("source", "")
                    await self.rate_limiter.acquire(source)

                    await broadcast({"type": "status", "data": {
                        "current_action": f"Applying: {job.get('title')} @ {job.get('company')}"
                    }})

                    applier = self._get_applier(source)
                    if not applier:
                        db = db_session_factory()
                        await save_job(db, job, "failed", "No applier for source")
                        db.close()
                        self.stats["failed"] += 1
                        continue

                    success, reason = await applier.apply(job)

                    db = db_session_factory()
                    try:
                        status = "applied" if success else "failed"
                        await save_job(db, job, status, None if success else reason)
                    finally:
                        db.close()

                    if success:
                        self.stats["applied"] += 1
                        await broadcast({"type": "applied", "data": {
                            "title": job.get("title"),
                            "company": job.get("company"),
                            "source": source,
                            "ats_score": job.get("ats_score"),
                        }})
                        await broadcast({"type": "log", "data": {
                            "message": f"[{worker_id}] ✓ Applied: {job.get('title')} @ {job.get('company')}",
                            "level": "success",
                        }})
                    else:
                        self.stats["failed"] += 1
                        item.retries += 1
                        if item.retries < 2 and "login" not in reason.lower():
                            await asyncio.sleep(2 ** item.retries * 5)
                            await self._apply_queue.put(item)
                        else:
                            self._dead_letter.append({**job, "failure_reason": reason})
                            self.stats["dead_letters"] += 1
                            await broadcast({"type": "log", "data": {
                                "message": f"[{worker_id}] ✗ Failed: {reason[:100]}",
                                "level": "error",
                            }})

                    # Human-like delay between applications
                    import random
                    await asyncio.sleep(random.uniform(20, 60))

                except Exception as e:
                    logger.error(f"[{worker_id}] Apply error: {e}", exc_info=True)
                    self.stats["failed"] += 1
                finally:
                    self._apply_queue.task_done()

    def _get_applier(self, source: str):
        from .applier.linkedin import LinkedInApplier
        from .applier.indeed import IndeedApplier
        registry = {
            "linkedin": LinkedInApplier,
            "indeed": IndeedApplier,
        }
        cls = registry.get(source)
        return cls() if cls else None

    def get_stats(self) -> dict:
        return {
            **self.stats,
            "queue_size": self.queue_size,
            "resume_queue_size": self._resume_queue.qsize(),
            "apply_queue_size": self._apply_queue.qsize(),
            "dead_letter_count": len(self._dead_letter),
        }
