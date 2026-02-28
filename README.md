# JobApply AI — Autonomous Job Application Platform

An agentic AI system that finds, evaluates, and applies to jobs on your behalf — 24/7, at scale, before your competition even sees them on LinkedIn.

---

## What It Does

```
Every 15 minutes:
  1. Scrape jobs from ATS APIs directly (Greenhouse, Lever, Ashby) — 2–24h before LinkedIn
  2. Monitor your target companies across ALL their ATS platforms simultaneously
  3. Run every job through an AI agent pipeline:
       ├── Fit Scoring   (claude-sonnet-4-6: 0–100 score, skip if below threshold)
       ├── Company Intel (claude-haiku: funding, culture, talking points)
       └── Cover Letter  (claude-sonnet-4-6: tailored per job, saves to file)
  4. Rebuild your resume in AI for each role (ATS-optimized PDF, keyword-matched)
  5. Submit applications via stealth Playwright browser (anti-detection, cookie persistence)
  6. Track outcomes: follow-ups, recruiter replies, interviews, offers
```

---

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        JobApply AI Platform                          │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  React SPA   │  │  FastAPI     │  │  SQLite DB               │  │
│  │  Dashboard   │◄─│  Backend     │◄─│  (applications,          │  │
│  │  :5173/:8000 │  │  :8000       │  │   outcomes, tracking)    │  │
│  └──────────────┘  └──────┬───────┘  └──────────────────────────┘  │
│                            │ WebSocket (real-time events)            │
│              ┌─────────────┼─────────────┐                          │
│              ▼             ▼             ▼                           │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                   Automation Scheduler                       │    │
│  │                                                              │    │
│  │  Tier 1 (every 15min): Greenhouse · Lever · Ashby · Dice   │    │
│  │  Tier 2 (every 15min): Company Watchlist (all ATS)          │    │
│  │  Tier 3 (every 30min): LinkedIn · Indeed · Glassdoor        │    │
│  │  Tier 4 (session start): Hiring Signal Detection             │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                            │                                         │
│                            ▼                                         │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │              Priority Queue Pipeline                         │    │
│  │                                                              │    │
│  │  job_heap → agent_queue → resume_queue → apply_queue → DB  │    │
│  │              │                │               │              │    │
│  │         AI Agents        PDF Builder    Stealth Browser      │    │
│  │         (fit/CL/intel)  (ATS-optimized) (anti-detection)    │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### Tiered Sourcing Strategy

The key insight: **LinkedIn is an aggregator — jobs appear there 2–24 hours after being posted on company ATS platforms.** The system is designed to get there first.

| Tier | Sources | Advantage | Frequency |
|------|---------|-----------|-----------|
| **Tier 1** | Greenhouse API, Lever API, Ashby GraphQL, Remotive, Dice, ZipRecruiter | 2–24h before LinkedIn | Every 15 min |
| **Tier 2** | Company Watchlist (all ATS) | Real-time monitoring of YOUR target companies | Every 15 min |
| **Tier 3** | LinkedIn, Indeed, Glassdoor | Wide reach but high competition | Every 30 min |
| **Tier 4** | Hiring Signal Detector (Claude) | Predicts roles BEFORE they're posted | Session startup |

### AI Agent Pipeline

Every scraped job passes through this pipeline before an application is submitted:

```
scraped job
    │
    ▼
JobFitAgent (claude-sonnet-4-6)
    │ Scores fit 0–100 against your profile
    │ If score < min_fit_score (default: 65) → dead-letter (skip)
    │
    ▼
CompanyResearchAgent (claude-haiku)
    │ Culture, tech stack, recent news, growth stage
    │ Results embedded into cover letter context
    │
    ▼
CoverLetterAgent (claude-sonnet-4-6)
    │ Personalized letter referencing company research
    │ Saved as .txt file + stored in DB
    │
    ▼
ResumeGenerator (OpenAI GPT-4o + ReportLab)
    │ Tailors your profile to this specific job's keywords
    │ Builds ATS-safe single-column PDF
    │ ATS score = % of required skills matched
    │ If ATS score < min_ats_score → skip
    │
    ▼
Applier (Playwright stealth browser)
    │ LinkedIn Easy Apply or Indeed Apply
    │ Session cookies persisted between runs
    │
    ▼
Database + WebSocket broadcast
```

### Stealth Browser Anti-Detection

The Playwright browser implements 13 anti-detection layers:

1. `navigator.webdriver = undefined`
2. Realistic plugin/MIME-type list
3. Language, platform, hardware spoofing
4. Chrome runtime injection
5. Permissions API passthrough
6. Canvas fingerprint noise (pixel jitter)
7. WebGL renderer spoofing (Intel Iris)
8. HeadlessChrome UA replacement
9. Realistic screen color/pixel depth
10. Network connection spoofing
11. Poisson-distributed delays (not uniform random)
12. Bezier-curve mouse movement (Python-tracked, not JS)
13. Gaussian-speed typing with 2% typo+correction rate

Session cookies are saved to `sessions/{platform}/state.json` and restored on next run — avoids repeated login challenges.

---

## Setup

### Option A: Docker (Recommended)

```bash
# 1. Clone and configure
git clone <repo> jobapply
cd jobapply

cp .env.example .env
# Edit .env — set your API keys and credentials
nano .env

# Edit your profile
nano user_profile.yaml

# 2. Build and run
docker-compose up --build

# Dashboard: http://localhost:8000
```

### Option B: Local (Development)

**Prerequisites:** Python 3.11+, Node 18+

```bash
cd jobapply

# Backend
python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium

# Frontend
cd frontend
npm install
npm run build
cd ..

# Configure
cp .env.example .env
nano .env
nano user_profile.yaml

# Start
./start.sh
```

---

## Configuration

### `.env` Reference

```bash
# ── AI Keys ────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...      # Required: fit scoring, cover letters, signals
OPENAI_API_KEY=sk-...             # Required: resume tailoring (GPT-4o)
OPENAI_MODEL=gpt-4o               # Optional: default gpt-4o

# ── Job Platform Credentials ───────────────────────────────────────────────
LINKEDIN_EMAIL=you@email.com
LINKEDIN_PASSWORD=yourpassword
INDEED_EMAIL=you@email.com
INDEED_PASSWORD=yourpassword

# ── Application Settings ───────────────────────────────────────────────────
MIN_FIT_SCORE=65                  # 0–100, skip jobs below this (default: 65)
MIN_ATS_SCORE=50                  # % of required skills matched (default: 50)
MAX_APPLICATIONS_PER_RUN=20       # Safety cap per session
FOLLOWUP_AFTER_DAYS=7             # Days before suggesting follow-up email
HEADLESS=true                     # false = see the browser (debug mode)

# ── Proxy (optional) ───────────────────────────────────────────────────────
PROXY_LIST=http://user:pass@host:port,http://...

# ── CORS ───────────────────────────────────────────────────────────────────
CORS_ORIGINS=http://localhost:5173,http://localhost:8000
```

### `user_profile.yaml` Reference

This is your "base resume" — fill it out completely. The AI will tailor it for each job.

Key sections:
- **Personal info**: name, email, phone, address
- **Skills**: ordered by strength (most important first)
- **Experience**: reverse-chronological, with achievement bullets
- **Projects**: tech side projects with impact metrics
- **Education**: degrees, GPA
- **Certifications**: AWS, GCP, etc.

---

## API Reference

### Automation Control
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/start` | Start automation with `AutomationConfig` body |
| `POST` | `/api/stop` | Stop running automation |
| `GET` | `/api/status` | Current run status + counters |

### Jobs
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/jobs` | List applications (filterable by status, source, company) |
| `GET` | `/api/jobs/{id}` | Single application detail |
| `GET` | `/api/jobs/{id}/resume` | Download generated resume PDF |
| `GET` | `/api/jobs/{id}/cover-letter` | Download cover letter |
| `PATCH` | `/api/jobs/{id}/outcome` | Update outcome: interview/offer/rejected |
| `DELETE` | `/api/jobs/{id}` | Delete application record |

### Analytics
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/stats` | Aggregate stats: applied, failed, avg ATS/fit scores, by source |
| `GET` | `/api/agents/stats` | AI pipeline stats: evaluated, approved, skipped, cover letters |

### Follow-ups
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/followups` | Jobs needing follow-up emails (AI-drafted) |
| `POST` | `/api/followups/{id}/sent` | Mark follow-up as sent |
| `POST` | `/api/followups/{id}/replied` | Mark recruiter replied |

### Outreach
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/outreach/signal` | Generate cold outreach triggered by hiring signal |
| `POST` | `/api/outreach/speculative` | Generate speculative outreach for watchlist company |
| `POST` | `/api/signals/detect` | Run hiring signal detection on a list of companies |

### AutomationConfig Schema
```json
{
  "search_keywords": ["software engineer", "backend engineer"],
  "locations": ["San Francisco", "New York", "Remote"],
  "remote_only": false,
  "sources": ["greenhouse", "lever", "ashby", "watchlist", "linkedin", "indeed"],
  "target_companies": ["stripe", "linear", "vercel", "anthropic"],
  "blocked_companies": ["Amazon", "Oracle"],
  "job_types": ["full-time"],
  "experience_level": ["senior", "mid"],
  "check_interval_minutes": 15,
  "max_applications_per_run": 20,
  "min_ats_score": 50,
  "min_fit_score": 65,
  "enable_cover_letter": true,
  "enable_signals": true,
  "followup_after_days": 7,
  "auto_apply": true
}
```

---

## Project Structure

```
jobapply/
├── backend/
│   ├── agents/
│   │   ├── job_fit.py           # Claude: 0–100 fit scoring per job
│   │   ├── company_research.py  # Claude: company intel (culture, funding, news)
│   │   ├── cover_letter.py      # Claude: personalized cover letter
│   │   ├── followup.py          # Claude: follow-up email drafts
│   │   ├── orchestrator.py      # Chains all agents; gates on fit score
│   │   ├── signal_detector.py   # Claude: hiring signals (funding, headcount)
│   │   └── outreach.py          # Claude: cold outreach (LinkedIn + email)
│   │
│   ├── applier/
│   │   ├── stealth_browser.py   # Playwright + 13 anti-detection layers
│   │   ├── form_filler.py       # Generic form filling engine
│   │   ├── linkedin.py          # LinkedIn Easy Apply automation
│   │   ├── indeed.py            # Indeed Apply automation
│   │   └── base.py              # BaseApplier interface
│   │
│   ├── scraper/
│   │   ├── base.py              # BaseScraper with _fetch_json, _is_recent
│   │   ├── greenhouse.py        # Greenhouse boards API (Stripe, Figma, etc.)
│   │   ├── lever.py             # Lever REST API (Netflix, Shopify, etc.)
│   │   ├── ashby.py             # Ashby GraphQL (Anthropic, OpenAI, Vercel, etc.)
│   │   ├── company_watchlist.py # Monitor target companies across all ATS
│   │   ├── linkedin.py          # LinkedIn Jobs scraper
│   │   ├── indeed.py            # Indeed scraper
│   │   ├── remotive.py          # Remote jobs
│   │   ├── dice.py              # Dice.com
│   │   └── ziprecruiter.py      # ZipRecruiter
│   │
│   ├── resume/
│   │   ├── generator.py         # OpenAI-powered resume tailoring
│   │   ├── pdf_builder.py       # ReportLab ATS-safe PDF generation
│   │   └── jd_parser.py         # Job description skill/requirement extraction
│   │
│   ├── main.py                  # FastAPI app + all endpoints
│   ├── scheduler.py             # Tiered scraping loop + signal detection
│   ├── queue_manager.py         # Priority queue + worker orchestration
│   ├── models.py                # SQLAlchemy ORM models
│   ├── schemas.py               # Pydantic schemas
│   ├── config.py                # Settings from .env + profile loader
│   └── database.py              # SQLite init + session factory
│
├── frontend/                    # React + Vite + Tailwind dashboard
├── sessions/                    # Browser session cookies (git-ignored)
├── resumes/                     # Generated PDF resumes (git-ignored)
├── cover_letters/               # Generated cover letters (git-ignored)
├── user_profile.yaml            # YOUR resume profile (edit this)
├── .env                         # API keys and credentials (git-ignored)
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Multi-stage: Node build + Python runtime
├── docker-compose.yml           # Single-command startup
└── start.sh                     # Local development startup script
```

---

## How the Queue Pipeline Works

```
Scrapers produce jobs → job_heap (priority queue, newest first)
                             │
                    dispatcher (rate-limited per domain)
                             │
                      agent_queue (maxsize=300)
                             │
              ┌──── AI Agent Workers (x2) ────┐
              │  JobFitAgent → skip if <65     │
              │  CompanyResearchAgent          │
              │  CoverLetterAgent              │
              └──────────────┬────────────────┘
                             │ approved jobs only
                      resume_queue (maxsize=200)
                             │
              ┌──── Resume Workers (x3) ───────┐
              │  JDParser → skill extraction   │
              │  OpenAI → tailored content     │
              │  ReportLab → ATS PDF           │
              │  ATS score check (skip if low) │
              └──────────────┬────────────────┘
                             │
                       apply_queue (maxsize=200)
                             │
              ┌──── Apply Workers (x2) ────────┐
              │  Stealth browser apply         │
              │  Retry x1 on transient failure │
              │  Dead-letter on permanent fail │
              └──────────────┬────────────────┘
                             │
                    Database + WebSocket broadcast
```

**Dead-letter queue**: Jobs that fail permanently (after retries, or on agent errors) land here. Inspectable via the dashboard.

---

## Hiring Signal Detection

At session startup, Claude analyzes your `target_companies` list for:

- **Funding rounds** — Series A/B/C in the last 12 months signals headcount growth
- **Executive hires** — New VP Eng / CTO / Head of Product signals team buildout
- **Headcount growth** — Rapid LinkedIn headcount increase
- **Product launches** — New features/products signal engineering surge

Returns companies with `signal_strength: high|medium|low` and `outreach_urgency: now|soon|monitor`.

Use the outreach API endpoints to generate personalized cold LinkedIn/email messages timed to the signal.

---

## Direct Outreach (Bypass Job Boards)

For high-signal companies, generate cold outreach before a role is posted:

```bash
# Signal-triggered outreach
curl -X POST http://localhost:8000/api/outreach/signal \
  -H "Content-Type: application/json" \
  -d '{
    "company": "Linear",
    "signal_summary": "Raised $35M Series B last month",
    "signal_type": "funding",
    "predicted_roles": ["Senior Backend Engineer", "Staff Engineer"]
  }'
# Returns: linkedin_message (300 chars), email_subject, email_body

# Speculative outreach for watchlist company
curl -X POST http://localhost:8000/api/outreach/speculative \
  -d '{"company": "Vercel", "department": "Platform Engineering"}'
```

---

## Follow-up Tracking

After applying, the system tracks recruiter responses:

```bash
# Get jobs needing follow-up (7+ days with no reply)
GET /api/followups?after_days=7
# Returns AI-drafted follow-up email for each job

# Mark follow-up sent
POST /api/followups/{id}/sent

# Mark recruiter replied
POST /api/followups/{id}/replied

# Update outcome
PATCH /api/jobs/{id}/outcome
{"outcome": "interview", "notes": "Phone screen scheduled for Thursday"}
```

---

## Security Notes

- **Credentials**: Never commit `.env`. It's in `.gitignore`.
- **Session files**: `sessions/` contains browser cookies. Keep private.
- **Rate limits**: The system respects per-domain rate limits. Do not set `check_interval_minutes` below 10 or you risk IP bans.
- **LinkedIn ToS**: Automation of LinkedIn violates their Terms of Service. Use at your own risk. The stealth browser minimizes detection risk but does not eliminate it.
- **Proxy**: For large-scale use, configure `PROXY_LIST` in `.env` to rotate IPs.

---

## Troubleshooting

**"CAPTCHA detected"**: The stealth browser hit a bot challenge.
- Reduce `check_interval_minutes` to slow down
- Add proxies via `PROXY_LIST`
- Set `HEADLESS=false` to debug visually

**Low ATS scores**: Your `user_profile.yaml` skills don't match the JD keywords.
- Lower `MIN_ATS_SCORE` temporarily
- Add more skills to your profile

**Agent skipping too many jobs**: `MIN_FIT_SCORE` is too high.
- Try lowering it to 55–60 in `.env`

**LinkedIn login fails**: Session cookies may be expired.
- Delete `sessions/linkedin/state.json` to force fresh login
- Check credentials in `.env`

**Resume PDFs not generating**: OpenAI key missing or quota exceeded.
- The system falls back to profile-direct resume (no AI tailoring)
- Set `OPENAI_API_KEY` in `.env`
