import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
PROFILE_PATH = BASE_DIR / "user_profile.yaml"
RESUMES_DIR = BASE_DIR / "resumes"
RESUMES_DIR.mkdir(exist_ok=True)


def load_user_profile() -> dict:
    if PROFILE_PATH.exists():
        with open(PROFILE_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    return {}


class Settings:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

    # Anthropic / Claude settings
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Agent settings
    MIN_FIT_SCORE: int = int(os.getenv("MIN_FIT_SCORE", "65"))
    FOLLOWUP_AFTER_DAYS: int = int(os.getenv("FOLLOWUP_AFTER_DAYS", "7"))
    LINKEDIN_EMAIL: str = os.getenv("LINKEDIN_EMAIL", "")
    LINKEDIN_PASSWORD: str = os.getenv("LINKEDIN_PASSWORD", "")
    INDEED_EMAIL: str = os.getenv("INDEED_EMAIL", "")
    INDEED_PASSWORD: str = os.getenv("INDEED_PASSWORD", "")
    GLASSDOOR_EMAIL: str = os.getenv("GLASSDOOR_EMAIL", "")
    GLASSDOOR_PASSWORD: str = os.getenv("GLASSDOOR_PASSWORD", "")

    # Proxy settings (optional)
    PROXY_LIST: list = [p.strip() for p in os.getenv("PROXY_LIST", "").split(",") if p.strip()]

    # Browser settings
    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"
    SLOW_MO: int = int(os.getenv("SLOW_MO", "0"))

    # App settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "jobapply-secret-key-2024")
    CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]


settings = Settings()
