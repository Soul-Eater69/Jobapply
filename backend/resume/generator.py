"""
AI-powered resume generator.
Uses OpenAI to tailor the user's base profile to each job description,
then builds an ATS-friendly PDF.
"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from ..config import settings, load_user_profile, RESUMES_DIR
from .jd_parser import JDParser
from .pdf_builder import PDFBuilder

logger = logging.getLogger(__name__)


class ResumeGenerator:
    def __init__(self):
        self.parser = JDParser()
        self.pdf_builder = PDFBuilder()

    async def generate(self, job: dict) -> Dict[str, Any]:
        """
        Generate a tailored, ATS-friendly resume for the given job.
        Returns dict with: pdf_path, content, matched_skills, required_skills, ats_score
        """
        profile = load_user_profile()
        jd_text = job.get("description", "")

        # Parse JD
        jd_data = self.parser.parse(jd_text) if jd_text else {}
        required_skills = (jd_data.get("tech_stack") or []) + (jd_data.get("required_skills") or [])
        preferred_skills = jd_data.get("preferred_skills") or []
        user_skills = [s.lower() for s in profile.get("skills", [])]

        # Match skills
        matched_skills = [s for s in required_skills if s.lower() in user_skills]
        missing_skills = [s for s in required_skills if s.lower() not in user_skills]

        # ATS score: % of required skills matched
        ats_score = (len(matched_skills) / len(required_skills) * 100) if required_skills else 75.0
        ats_score = round(ats_score, 1)

        # Generate tailored resume content via OpenAI
        resume_content = await self._generate_with_ai(job, jd_data, profile, matched_skills, missing_skills)

        # Build PDF
        safe_company = "".join(c for c in job.get("company", "company") if c.isalnum() or c in "-_")[:30]
        safe_title = "".join(c for c in job.get("title", "role") if c.isalnum() or c in "-_")[:30]
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"{safe_company}_{safe_title}_{timestamp}.pdf"
        pdf_path = RESUMES_DIR / pdf_filename

        self.pdf_builder.build(
            resume_data=resume_content,
            profile=profile,
            output_path=str(pdf_path),
            job_title=job.get("title", ""),
            company=job.get("company", ""),
        )

        return {
            "pdf_path": str(pdf_path),
            "content": resume_content.get("summary", ""),
            "matched_skills": matched_skills[:20],
            "required_skills": required_skills[:20],
            "ats_score": ats_score,
            "jd_data": jd_data,
        }

    async def _generate_with_ai(
        self,
        job: dict,
        jd_data: dict,
        profile: dict,
        matched_skills: list,
        missing_skills: list,
    ) -> dict:
        """Use OpenAI to generate tailored resume sections."""

        if not settings.OPENAI_API_KEY:
            return self._fallback_resume(profile, job, matched_skills)

        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)

            prompt = self._build_prompt(job, jd_data, profile, matched_skills)

            # Run in thread to not block async loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    max_tokens=3000,
                    temperature=0.4,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert resume writer and ATS optimization specialist. Always respond with valid JSON only.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                )
            )

            raw = response.choices[0].message.content.strip()
            return self._parse_ai_response(raw, profile)

        except Exception as e:
            logger.error(f"AI resume generation failed: {e}")
            return self._fallback_resume(profile, job, matched_skills)

    def _build_prompt(self, job: dict, jd_data: dict, profile: dict, matched_skills: list) -> str:
        skills_str = ", ".join(profile.get("skills", [])[:30])
        required_str = ", ".join(jd_data.get("tech_stack", [])[:15])
        exp_str = "\n".join(
            f"- {e.get('title')} at {e.get('company')} ({e.get('duration', '')}): {e.get('description', '')}"
            for e in profile.get("experience", [])
        )
        projects_str = "\n".join(
            f"- {p.get('name')}: {p.get('description', '')} | Tech: {', '.join(p.get('tech', []))}"
            for p in profile.get("projects", [])
        )
        edu_str = "\n".join(
            f"- {e.get('degree')} in {e.get('field')} from {e.get('school')} ({e.get('year', '')})"
            for e in profile.get("education", [])
        )

        return f"""You are an expert resume writer and ATS optimization specialist.
Create a highly tailored, ATS-friendly resume for this specific job application.

═══ JOB DETAILS ════════════════════════════════════════════════════════
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}

Job Description:
{(job.get('description', ''))[:2000]}

Required Skills Detected: {required_str}
Experience Level: {jd_data.get('experience_level', 'mid')}
Key Responsibilities: {'; '.join(jd_data.get('key_responsibilities', [])[:5])}

═══ CANDIDATE PROFILE ══════════════════════════════════════════════════
Name: {profile.get('first_name', '')} {profile.get('last_name', '')}
Current Role: {profile.get('current_role', '')}
Years Experience: {profile.get('years_experience', '')}
All Skills: {skills_str}

Work Experience:
{exp_str}

Projects:
{projects_str}

Education:
{edu_str}

═══ INSTRUCTIONS ════════════════════════════════════════════════════════
Generate a tailored resume in this EXACT JSON format:

{{
  "summary": "2-3 sentence professional summary that directly addresses the job requirements and uses keywords from the JD",
  "skills": ["skill1", "skill2", ...],  // Ordered by relevance to THIS job, max 16
  "experience": [
    {{
      "title": "Job Title",
      "company": "Company Name",
      "duration": "Month Year – Month Year",
      "location": "City, State",
      "bullets": [
        "Achievement-focused bullet starting with action verb, quantified where possible",
        "Tailored to mirror language from the job description",
        "3-5 bullets per role"
      ]
    }}
  ],
  "projects": [
    {{
      "name": "Project Name",
      "description": "One sentence tailored description highlighting relevant aspects",
      "tech": ["tech1", "tech2"]
    }}
  ],
  "education": [
    {{
      "degree": "Degree",
      "field": "Field of Study",
      "school": "University Name",
      "year": "Year"
    }}
  ]
}}

Rules:
- Use ACTION VERBS (Built, Designed, Led, Implemented, Optimized, Reduced, Increased...)
- Mirror keywords and phrases from the job description naturally
- Quantify achievements (%, $, ms, users, etc.) wherever possible
- Keep bullets concise (max 15 words each)
- Only include skills actually in the candidate's profile
- Order experience reverse-chronologically
- Output ONLY valid JSON, no markdown, no explanation"""

    def _parse_ai_response(self, raw: str, profile: dict) -> dict:
        import json
        import re

        # Extract JSON from response
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return self._fallback_resume(profile, {}, [])

    def _fallback_resume(self, profile: dict, job: dict, matched_skills: list) -> dict:
        """Fallback when AI is not available — use profile data directly."""
        return {
            "summary": profile.get("summary", f"Experienced {profile.get('current_role', 'professional')} "
                                   f"with {profile.get('years_experience', '')} years of experience."),
            "skills": (matched_skills + profile.get("skills", []))[:16],
            "experience": profile.get("experience", []),
            "projects": profile.get("projects", []),
            "education": profile.get("education", []),
        }
