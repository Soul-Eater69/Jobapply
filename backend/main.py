import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from .database import init_db, get_db
from .models import JobApplication
from .schemas import JobApplicationOut, JobStats, AutomationConfig, RunStatus
from .config import settings, BASE_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global automation state
automation_state = {
    "running": False,
    "task": None,
    "config": None,
    "jobs_found": 0,
    "jobs_applied": 0,
    "jobs_failed": 0,
    "current_action": "idle",
    "started_at": None,
    "last_check": None,
}

# WebSocket connections pool
ws_connections: List[WebSocket] = []


async def broadcast(message: dict):
    dead = []
    for ws in ws_connections:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_connections.remove(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialized")
    yield
    if automation_state["task"]:
        automation_state["task"].cancel()


app = FastAPI(title="JobApply Automation", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── WebSocket ───────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_connections.append(websocket)
    # Send initial state
    await websocket.send_json({
        "type": "status",
        "data": {
            "running": automation_state["running"],
            "current_action": automation_state["current_action"],
            "jobs_found": automation_state["jobs_found"],
            "jobs_applied": automation_state["jobs_applied"],
            "jobs_failed": automation_state["jobs_failed"],
        }
    })
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_connections.remove(websocket)


# ─── Stats ────────────────────────────────────────────────────────────────────

@app.get("/api/stats", response_model=JobStats)
def get_stats(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)

    total = db.query(func.count(JobApplication.id)).scalar()
    applied = db.query(func.count(JobApplication.id)).filter(JobApplication.status == "applied").scalar()
    failed = db.query(func.count(JobApplication.id)).filter(JobApplication.status == "failed").scalar()
    pending = db.query(func.count(JobApplication.id)).filter(JobApplication.status == "pending").scalar()
    skipped = db.query(func.count(JobApplication.id)).filter(JobApplication.status == "skipped").scalar()
    today = db.query(func.count(JobApplication.id)).filter(JobApplication.applied_at >= today_start).scalar()
    this_week = db.query(func.count(JobApplication.id)).filter(JobApplication.applied_at >= week_start).scalar()
    avg_ats = db.query(func.avg(JobApplication.ats_score)).filter(JobApplication.ats_score.isnot(None)).scalar()

    top_companies_raw = (
        db.query(JobApplication.company, func.count(JobApplication.id).label("count"))
        .group_by(JobApplication.company)
        .order_by(desc("count"))
        .limit(10)
        .all()
    )
    top_companies = [{"company": r[0], "count": r[1]} for r in top_companies_raw]

    by_source_raw = (
        db.query(JobApplication.source, func.count(JobApplication.id).label("count"))
        .group_by(JobApplication.source)
        .all()
    )
    by_source = [{"source": r[0], "count": r[1]} for r in by_source_raw]

    by_status_raw = (
        db.query(JobApplication.status, func.count(JobApplication.id).label("count"))
        .group_by(JobApplication.status)
        .all()
    )
    by_status = [{"status": r[0], "count": r[1]} for r in by_status_raw]

    return JobStats(
        total=total or 0,
        applied=applied or 0,
        failed=failed or 0,
        pending=pending or 0,
        skipped=skipped or 0,
        today=today or 0,
        this_week=this_week or 0,
        avg_ats_score=round(avg_ats, 1) if avg_ats else None,
        top_companies=top_companies,
        by_source=by_source,
        by_status=by_status,
    )


# ─── Jobs ─────────────────────────────────────────────────────────────────────

@app.get("/api/jobs", response_model=List[JobApplicationOut])
def get_jobs(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    source: Optional[str] = None,
    company: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(JobApplication)
    if status:
        q = q.filter(JobApplication.status == status)
    if source:
        q = q.filter(JobApplication.source == source)
    if company:
        q = q.filter(JobApplication.company.ilike(f"%{company}%"))
    if search:
        q = q.filter(
            JobApplication.title.ilike(f"%{search}%") |
            JobApplication.company.ilike(f"%{search}%") |
            JobApplication.description.ilike(f"%{search}%")
        )
    return q.order_by(desc(JobApplication.scraped_at)).offset(skip).limit(limit).all()


@app.get("/api/jobs/{job_id}", response_model=JobApplicationOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(JobApplication).filter(JobApplication.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(JobApplication).filter(JobApplication.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()
    return {"message": "Deleted"}


@app.get("/api/jobs/{job_id}/resume")
def get_resume(job_id: int, db: Session = Depends(get_db)):
    job = db.query(JobApplication).filter(JobApplication.id == job_id).first()
    if not job or not job.resume_path:
        raise HTTPException(status_code=404, detail="Resume not found")
    from pathlib import Path
    path = Path(job.resume_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume file missing")
    return FileResponse(str(path), media_type="application/pdf", filename=path.name)


# ─── Automation Control ───────────────────────────────────────────────────────

@app.post("/api/start")
async def start_automation(config: AutomationConfig, db: Session = Depends(get_db)):
    if automation_state["running"]:
        raise HTTPException(status_code=400, detail="Automation already running")

    automation_state["running"] = True
    automation_state["config"] = config.model_dump()
    automation_state["jobs_found"] = 0
    automation_state["jobs_applied"] = 0
    automation_state["jobs_failed"] = 0
    automation_state["started_at"] = datetime.utcnow()
    automation_state["current_action"] = "Starting automation..."

    async def run():
        from .scheduler import run_automation_loop
        try:
            await run_automation_loop(config, db, automation_state, broadcast)
        except asyncio.CancelledError:
            logger.info("Automation cancelled")
        except Exception as e:
            logger.error(f"Automation error: {e}", exc_info=True)
        finally:
            automation_state["running"] = False
            automation_state["current_action"] = "idle"
            await broadcast({"type": "stopped", "data": {"reason": "Automation finished"}})

    automation_state["task"] = asyncio.create_task(run())
    return {"message": "Automation started"}


@app.post("/api/stop")
async def stop_automation():
    if not automation_state["running"]:
        raise HTTPException(status_code=400, detail="Not running")

    if automation_state["task"]:
        automation_state["task"].cancel()

    automation_state["running"] = False
    automation_state["current_action"] = "idle"
    await broadcast({"type": "stopped", "data": {"reason": "Manually stopped"}})
    return {"message": "Automation stopped"}


@app.get("/api/status", response_model=RunStatus)
def get_status():
    return RunStatus(
        running=automation_state["running"],
        jobs_found_session=automation_state["jobs_found"],
        jobs_applied_session=automation_state["jobs_applied"],
        jobs_failed_session=automation_state["jobs_failed"],
        current_action=automation_state["current_action"],
        started_at=automation_state["started_at"],
        last_check=automation_state["last_check"],
    )


# ─── Config / Profile ─────────────────────────────────────────────────────────

@app.get("/api/profile")
def get_profile():
    from .config import load_user_profile
    return load_user_profile()


@app.post("/api/profile")
async def update_profile(data: dict):
    import yaml
    from .config import PROFILE_PATH
    with open(PROFILE_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    return {"message": "Profile updated"}


# Serve frontend in production
frontend_dist = BASE_DIR / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
