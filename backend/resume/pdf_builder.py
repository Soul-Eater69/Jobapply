"""
ATS-friendly PDF Resume Builder using ReportLab.
Design principles:
  - Single column layout (ATS parsers hate multi-column)
  - No images, tables, headers/footers, or text boxes
  - Consistent fonts (Helvetica family — universally parsed)
  - Clear section headings with underlines (not boxes)
  - Clean bullet points (hyphens — ATS safe)
  - Standard section names ATS scanners recognize
"""
import logging
from pathlib import Path
from typing import Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    KeepTogether,
)
from reportlab.lib.styles import ParagraphStyle

logger = logging.getLogger(__name__)

# Color palette — minimal, professional
BLACK = colors.HexColor("#000000")
DARK_GRAY = colors.HexColor("#2C2C2C")
MEDIUM_GRAY = colors.HexColor("#555555")
LIGHT_GRAY = colors.HexColor("#888888")
ACCENT = colors.HexColor("#1A3A5C")  # Dark navy — subtle, not distracting

# Fonts
FONT_NORMAL = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_ITALIC = "Helvetica-Oblique"

MARGINS = 0.65 * inch


def _style(name, **kwargs) -> ParagraphStyle:
    defaults = dict(fontName=FONT_NORMAL, fontSize=10, textColor=DARK_GRAY, leading=13, spaceAfter=0, spaceBefore=0)
    defaults.update(kwargs)
    return ParagraphStyle(name, **defaults)


STYLES = {
    "name": _style("name", fontName=FONT_BOLD, fontSize=22, textColor=BLACK, leading=26, alignment=TA_CENTER, spaceAfter=2),
    "contact": _style("contact", fontSize=9, textColor=MEDIUM_GRAY, leading=12, alignment=TA_CENTER, spaceAfter=6),
    "section_header": _style("section_header", fontName=FONT_BOLD, fontSize=11, textColor=ACCENT, leading=14, spaceBefore=10, spaceAfter=2),
    "job_title": _style("job_title", fontName=FONT_BOLD, fontSize=10, textColor=BLACK, leading=13, spaceAfter=0),
    "job_company": _style("job_company", fontSize=10, textColor=DARK_GRAY, leading=13),
    "job_meta": _style("job_meta", fontSize=9, textColor=MEDIUM_GRAY, leading=12, spaceAfter=3, fontName=FONT_ITALIC),
    "bullet": _style("bullet", fontSize=9.5, textColor=DARK_GRAY, leading=13, leftIndent=12, spaceAfter=2),
    "skills_text": _style("skills_text", fontSize=9.5, textColor=DARK_GRAY, leading=13, spaceAfter=2),
    "summary": _style("summary", fontSize=10, textColor=DARK_GRAY, leading=14, spaceAfter=4),
    "project_name": _style("project_name", fontName=FONT_BOLD, fontSize=10, textColor=BLACK, leading=13),
    "project_desc": _style("project_desc", fontSize=9.5, textColor=DARK_GRAY, leading=13, spaceAfter=2),
    "edu_school": _style("edu_school", fontName=FONT_BOLD, fontSize=10, textColor=BLACK, leading=13),
    "edu_degree": _style("edu_degree", fontSize=9.5, textColor=DARK_GRAY, leading=13, spaceAfter=2),
}


def _divider() -> HRFlowable:
    return HRFlowable(width="100%", thickness=0.5, color=ACCENT, spaceAfter=4, spaceBefore=2)


class PDFBuilder:

    def build(
        self,
        resume_data: dict,
        profile: dict,
        output_path: str,
        job_title: str = "",
        company: str = "",
    ):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            leftMargin=MARGINS,
            rightMargin=MARGINS,
            topMargin=MARGINS,
            bottomMargin=MARGINS,
            title=f"{profile.get('first_name', '')} {profile.get('last_name', '')} — {job_title}",
            author=f"{profile.get('first_name', '')} {profile.get('last_name', '')}",
            subject=f"Application for {job_title} at {company}",
            creator="JobApply AI",
        )

        story = []

        # ── Header ───────────────────────────────────────────────────────────
        name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        story.append(Paragraph(name, STYLES["name"]))

        # Contact line
        contact_parts = []
        if profile.get("phone"):
            contact_parts.append(profile["phone"])
        if profile.get("email"):
            contact_parts.append(profile["email"])
        if profile.get("linkedin_url"):
            url = profile["linkedin_url"].replace("https://", "").replace("http://", "")
            contact_parts.append(url)
        if profile.get("github_url"):
            url = profile["github_url"].replace("https://", "").replace("http://", "")
            contact_parts.append(url)
        if profile.get("portfolio_url"):
            url = profile["portfolio_url"].replace("https://", "").replace("http://", "")
            contact_parts.append(url)
        addr = profile.get("address", {})
        city_state = ", ".join(filter(None, [addr.get("city"), addr.get("state")]))
        if city_state:
            contact_parts.append(city_state)

        story.append(Paragraph(" | ".join(contact_parts), STYLES["contact"]))

        # ── Professional Summary ──────────────────────────────────────────────
        summary = resume_data.get("summary") or profile.get("summary", "")
        if summary:
            story.append(Spacer(1, 4))
            story.append(Paragraph("PROFESSIONAL SUMMARY", STYLES["section_header"]))
            story.append(_divider())
            story.append(Paragraph(summary, STYLES["summary"]))

        # ── Skills ────────────────────────────────────────────────────────────
        skills = resume_data.get("skills") or profile.get("skills", [])
        if skills:
            story.append(Paragraph("TECHNICAL SKILLS", STYLES["section_header"]))
            story.append(_divider())

            # Group skills into lines of ~5 each for readability
            chunks = [skills[i:i+5] for i in range(0, len(skills), 5)]
            for chunk in chunks:
                story.append(Paragraph(" • ".join(s.title() for s in chunk), STYLES["skills_text"]))
            story.append(Spacer(1, 4))

        # ── Work Experience ───────────────────────────────────────────────────
        experience = resume_data.get("experience") or profile.get("experience", [])
        if experience:
            story.append(Paragraph("WORK EXPERIENCE", STYLES["section_header"]))
            story.append(_divider())

            for exp in experience:
                block = []
                title = exp.get("title", "")
                company_name = exp.get("company", "")
                duration = exp.get("duration", "")
                location = exp.get("location", "")

                # Title + Company on same line (bold title)
                block.append(Paragraph(
                    f'<b>{title}</b> — {company_name}',
                    STYLES["job_title"]
                ))
                if duration or location:
                    meta = " | ".join(filter(None, [duration, location]))
                    block.append(Paragraph(meta, STYLES["job_meta"]))

                bullets = exp.get("bullets") or exp.get("highlights", [])
                for bullet in bullets:
                    if bullet.strip():
                        bullet_clean = bullet.lstrip("•-* ").strip()
                        block.append(Paragraph(f"– {bullet_clean}", STYLES["bullet"]))

                block.append(Spacer(1, 6))
                story.append(KeepTogether(block))

        # ── Projects ──────────────────────────────────────────────────────────
        projects = resume_data.get("projects") or profile.get("projects", [])
        if projects:
            story.append(Paragraph("PROJECTS", STYLES["section_header"]))
            story.append(_divider())

            for proj in projects[:4]:  # Max 4 projects
                block = []
                name = proj.get("name", "")
                desc = proj.get("description", "")
                tech = proj.get("tech", [])
                url = proj.get("url", "")

                tech_str = f" | Tech: {', '.join(t.title() for t in tech[:8])}" if tech else ""
                block.append(Paragraph(f"<b>{name}</b>{tech_str}", STYLES["project_name"]))

                if desc:
                    block.append(Paragraph(f"– {desc}", STYLES["project_desc"]))
                block.append(Spacer(1, 4))
                story.append(KeepTogether(block))

        # ── Education ─────────────────────────────────────────────────────────
        education = resume_data.get("education") or profile.get("education", [])
        if education:
            story.append(Paragraph("EDUCATION", STYLES["section_header"]))
            story.append(_divider())

            for edu in education:
                block = []
                degree = edu.get("degree", "")
                field = edu.get("field", "")
                school = edu.get("school", "")
                year = edu.get("year", "")
                gpa = edu.get("gpa", "")

                block.append(Paragraph(f"<b>{school}</b>", STYLES["edu_school"]))
                deg_str = f"{degree} in {field}" if field else degree
                gpa_str = f" | GPA: {gpa}" if gpa else ""
                year_str = f" | {year}" if year else ""
                block.append(Paragraph(f"{deg_str}{year_str}{gpa_str}", STYLES["edu_degree"]))
                block.append(Spacer(1, 4))
                story.append(KeepTogether(block))

        # ── Certifications (optional) ─────────────────────────────────────────
        certs = profile.get("certifications", [])
        if certs:
            story.append(Paragraph("CERTIFICATIONS", STYLES["section_header"]))
            story.append(_divider())
            for cert in certs:
                name = cert.get("name", cert) if isinstance(cert, dict) else cert
                issuer = cert.get("issuer", "") if isinstance(cert, dict) else ""
                year = cert.get("year", "") if isinstance(cert, dict) else ""
                parts = [name]
                if issuer:
                    parts.append(issuer)
                if year:
                    parts.append(str(year))
                story.append(Paragraph("– " + " | ".join(parts), STYLES["bullet"]))

        doc.build(story)
        logger.info(f"Resume PDF built: {output_path}")
