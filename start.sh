#!/bin/bash
# JobApply AI — Startup Script
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${BLUE}[JobApply]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

log "Starting JobApply AI Platform..."

# Check Python
if ! command -v python3 &>/dev/null; then
    error "Python 3 is required. Install it first."
fi

# Create/check virtual environment
if [ ! -d "venv" ]; then
    log "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# Install Python dependencies
log "Installing backend dependencies..."
pip install -q -r requirements.txt

# Install Playwright browsers (first time only)
if [ ! -d "$HOME/.cache/ms-playwright" ]; then
    log "Installing Playwright browsers (first time, may take a few minutes)..."
    playwright install chromium
    playwright install-deps chromium 2>/dev/null || true
fi

# Copy .env if it doesn't exist
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        warn ".env file created from .env.example. Please edit it with your credentials!"
        warn "Especially: ANTHROPIC_API_KEY, LINKEDIN_EMAIL, LINKEDIN_PASSWORD"
    fi
fi

# Build frontend if dist doesn't exist or package.json is newer
FRONTEND_DIR="$SCRIPT_DIR/frontend"
DIST_DIR="$FRONTEND_DIR/dist"

if [ -d "$FRONTEND_DIR" ]; then
    if [ ! -d "$DIST_DIR" ] || [ "$FRONTEND_DIR/package.json" -nt "$DIST_DIR/index.html" ]; then
        log "Building frontend..."
        if command -v node &>/dev/null && command -v npm &>/dev/null; then
            cd "$FRONTEND_DIR"
            npm install --silent
            npm run build --silent
            cd "$SCRIPT_DIR"
            success "Frontend built successfully"
        else
            warn "Node.js not found. Frontend will run in dev mode."
        fi
    fi
fi

success "All dependencies ready!"
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  JobApply AI is starting...${NC}"
echo -e "${GREEN}  Backend API:   http://localhost:8000${NC}"
echo -e "${GREEN}  Dashboard:     http://localhost:8000 (or http://localhost:5173)${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Start backend
if [ -d "$DIST_DIR" ]; then
    # Production mode: serve frontend from FastAPI
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
else
    # Dev mode: run backend + frontend separately
    log "Starting backend on :8000..."
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
    BACKEND_PID=$!

    log "Starting frontend dev server on :5173..."
    cd "$FRONTEND_DIR"
    npm run dev &
    FRONTEND_PID=$!

    trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
    wait
fi
