# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — Build React frontend
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json ./
# Use npm install (works with or without a lock file)
RUN npm install --silent

COPY frontend/ ./
RUN npm run build

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Python backend + Playwright
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# System deps required by Playwright Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget gnupg ca-certificates \
    libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 \
    fonts-liberation fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium
RUN playwright install chromium --with-deps

# Copy backend source
COPY backend/ ./backend/

# Copy built frontend
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Bake in a default user profile — overridable by volume mount at runtime
COPY user_profile.yaml ./user_profile.default.yaml

# Entrypoint handles dir creation + profile fallback
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
