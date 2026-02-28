"""
Job Description Parser.
Extracts skills, requirements, experience level, and key info from JD text.
Uses regex patterns + NLP heuristics for fast, offline parsing.
"""
import re
from typing import List, Dict, Any, Optional


# ─── Skill Taxonomy ──────────────────────────────────────────────────────────

TECH_SKILLS = {
    # Languages
    "python", "javascript", "typescript", "java", "golang", "go", "rust", "c++", "c#", "ruby",
    "php", "swift", "kotlin", "scala", "r", "matlab", "perl", "bash", "shell", "sql",
    # Frontend
    "react", "vue", "angular", "nextjs", "next.js", "svelte", "html", "css", "sass", "tailwind",
    "webpack", "vite", "redux", "graphql", "rest", "websocket",
    # Backend
    "node", "nodejs", "fastapi", "django", "flask", "express", "spring", "rails", "laravel",
    "grpc", "microservices", "kafka", "rabbitmq", "celery",
    # Cloud & DevOps
    "aws", "gcp", "azure", "docker", "kubernetes", "k8s", "terraform", "ansible", "ci/cd",
    "jenkins", "github actions", "circleci", "helm", "linux", "nginx", "apache",
    # Databases
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "cassandra", "dynamodb",
    "sqlite", "oracle", "bigquery", "snowflake", "spark", "hadoop",
    # ML/AI
    "machine learning", "deep learning", "tensorflow", "pytorch", "scikit-learn", "pandas",
    "numpy", "nlp", "computer vision", "transformers", "llm", "openai", "langchain",
    # Tools
    "git", "github", "jira", "agile", "scrum", "figma", "postman", "datadog", "grafana",
    "prometheus", "sentry", "splunk",
}

SOFT_SKILLS = {
    "communication", "leadership", "teamwork", "collaboration", "problem solving",
    "critical thinking", "time management", "adaptability", "creativity", "attention to detail",
    "project management", "mentoring", "stakeholder management",
}

EXPERIENCE_PATTERNS = [
    (r"(\d+)\+?\s*years?\s+of\s+(?:professional\s+)?experience", "years"),
    (r"(\d+)-(\d+)\s*years?\s+(?:of\s+)?experience", "years_range"),
    (r"at\s+least\s+(\d+)\s*years?", "years_min"),
    (r"minimum\s+(?:of\s+)?(\d+)\s*years?", "years_min"),
]

LEVEL_KEYWORDS = {
    "entry": ["entry", "junior", "jr", "0-2 years", "0-1 year", "new grad", "graduate", "associate"],
    "mid": ["mid", "intermediate", "3-5 years", "2-4 years", "2-5 years"],
    "senior": ["senior", "sr", "lead", "5+ years", "7+ years", "5-7 years", "experienced"],
    "staff": ["staff", "principal", "architect", "distinguished"],
    "manager": ["manager", "director", "head of", "vp", "vice president"],
}

SECTION_HEADERS = re.compile(
    r"(requirements?|qualifications?|what you.ll need|what we.re looking for|"
    r"skills?|responsibilities?|what you.ll do|about you|must[- ]have|nice[- ]to[- ]have|"
    r"preferred|bonus)",
    re.IGNORECASE,
)


class JDParser:

    def parse(self, jd_text: str) -> Dict[str, Any]:
        """Parse a job description and extract structured information."""
        text = jd_text.strip()
        text_lower = text.lower()

        return {
            "required_skills": self._extract_skills(text, required=True),
            "preferred_skills": self._extract_skills(text, required=False),
            "experience_years": self._extract_experience(text),
            "experience_level": self._detect_level(text_lower),
            "job_type": self._detect_job_type(text_lower),
            "remote": self._detect_remote(text_lower),
            "key_responsibilities": self._extract_responsibilities(text),
            "tech_stack": self._extract_tech_stack(text_lower),
            "keywords": self._extract_keywords(text),
            "education": self._extract_education(text_lower),
            "summary": self._generate_summary(text),
        }

    def _extract_skills(self, text: str, required: bool) -> List[str]:
        found = set()
        text_lower = text.lower()

        # Find required vs preferred section.
        # Boundary: next double-newline, next section header, or end of string.
        SECTION_BOUNDARY = r"(?=\n{2,}|\n[A-Z][A-Za-z ]{3,}:|\Z)"
        if required:
            req_match = re.search(
                r"(?:required|must[- ]have|qualifications?|requirements?)[:\s]*\n(.*?)" + SECTION_BOUNDARY,
                text, re.DOTALL | re.IGNORECASE
            )
            search_text = req_match.group(1).lower() if req_match else text_lower[:len(text_lower)//2]
        else:
            pref_match = re.search(
                r"(?:preferred|nice[- ]to[- ]have|bonus|plus|desired)[:\s]*\n(.*?)" + SECTION_BOUNDARY,
                text, re.DOTALL | re.IGNORECASE
            )
            search_text = pref_match.group(1).lower() if pref_match else text_lower[len(text_lower)//2:]

        for skill in TECH_SKILLS | SOFT_SKILLS:
            # Use word boundary for short skills
            pattern = r'\b' + re.escape(skill) + r'\b'
            if re.search(pattern, search_text):
                found.add(skill)

        return sorted(found)

    def _extract_experience(self, text: str) -> Optional[int]:
        for pattern, kind in EXPERIENCE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if kind == "years_range":
                    return int(match.group(2))  # Take upper bound
                return int(match.group(1))
        return None

    def _detect_level(self, text_lower: str) -> str:
        for level, keywords in LEVEL_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return level
        return "mid"

    def _detect_job_type(self, text_lower: str) -> str:
        if "part-time" in text_lower or "part time" in text_lower:
            return "part-time"
        if "contract" in text_lower or "freelance" in text_lower:
            return "contract"
        if "intern" in text_lower:
            return "internship"
        return "full-time"

    def _detect_remote(self, text_lower: str) -> bool:
        return any(w in text_lower for w in ["remote", "work from home", "wfh", "distributed team", "anywhere"])

    def _extract_responsibilities(self, text: str) -> List[str]:
        responsibilities = []
        lines = text.split("\n")
        in_resp_section = False

        for line in lines:
            line = line.strip()
            if re.search(r"(responsibilit|what you.ll do|your role|duties)", line, re.IGNORECASE):
                in_resp_section = True
                continue
            if in_resp_section:
                if SECTION_HEADERS.search(line) and "responsibilit" not in line.lower():
                    in_resp_section = False
                    continue
                if re.match(r"^[-•*]\s+.{10,}", line):
                    clean = re.sub(r"^[-•*]\s+", "", line)
                    responsibilities.append(clean)

        return responsibilities[:10]

    def _extract_tech_stack(self, text_lower: str) -> List[str]:
        found = []
        for skill in sorted(TECH_SKILLS):
            if re.search(r'\b' + re.escape(skill) + r'\b', text_lower):
                found.append(skill)
        return found[:20]

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract important noun phrases and keywords."""
        # Simple frequency-based extraction
        words = re.findall(r'\b[A-Z][a-zA-Z]{2,}\b', text)
        freq = {}
        for w in words:
            if len(w) > 3:
                freq[w.lower()] = freq.get(w.lower(), 0) + 1

        # Filter common words
        stopwords = {"this", "that", "with", "have", "will", "your", "our", "their", "from", "they", "what", "about"}
        keywords = [(w, c) for w, c in freq.items() if w not in stopwords and c >= 2]
        keywords.sort(key=lambda x: -x[1])
        return [w for w, _ in keywords[:15]]

    def _extract_education(self, text_lower: str) -> Optional[str]:
        if "phd" in text_lower or "doctorate" in text_lower:
            return "PhD"
        if "master" in text_lower or "ms " in text_lower or "m.s." in text_lower:
            return "Master's"
        if "bachelor" in text_lower or "bs " in text_lower or "b.s." in text_lower or "degree" in text_lower:
            return "Bachelor's"
        return None

    def _generate_summary(self, text: str) -> str:
        """Extract first meaningful paragraph as job summary."""
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 50]
        return paragraphs[0][:500] if paragraphs else text[:500]
