import io
import json
import logging
import os
import re
from pathlib import Path
from typing import Literal
from xml.sax.saxutils import escape

import httpx
from docx import Document
from docx.shared import Inches, Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from backend.altacv import build_altacv_pdf
from backend.latexcv import build_latexcv_pdf
from backend.resume_content import SECTIONS, contact_lines, experience_lines, has_content, personal_lines, section_text
from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)
app = FastAPI(title="Resume Genie")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class InterviewRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=100)
    model: str = Field(default=DEFAULT_MODEL, min_length=1, max_length=200)
    has_draft: bool = False


class InterviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    generate_resume: bool = Field(strict=True)


class ExperienceEntry(BaseModel):
    role: str = Field(default="", max_length=500)
    employer: str = Field(default="", max_length=500)
    client: str = Field(default="", max_length=500)
    dates: str = Field(default="", max_length=500)
    location: str = Field(default="", max_length=500)
    achievements: str = Field(default="", max_length=10000)
    technologies: str = Field(default="", max_length=2000)


class EducationEntry(BaseModel):
    qualification: str = Field(default="", max_length=500)
    institution: str = Field(default="", max_length=500)
    year: str = Field(default="", max_length=100)


class SkillGroup(BaseModel):
    category: str = Field(default="", max_length=500)
    skills: str = Field(default="", max_length=5000)


def remove_repeated_personal_details(details: str, passport_number: str, passport_valid_until: str, hobbies: str) -> str:
    aliases = {
        "passportnumber": "passport_number",
        "passportno": "passport_number",
        "passportvaliduntil": "passport_valid_until",
        "passportvalidity": "passport_valid_until",
        "validity": "passport_valid_until",
        "validuntil": "passport_valid_until",
        "passportexpiry": "passport_valid_until",
        "passportexpiration": "passport_valid_until",
        "hobby": "hobbies",
        "hobbies": "hobbies",
    }
    known_values = {
        key: re.sub(r"[^a-z0-9]", "", value.casefold())
        for key, value in (
            ("passport_number", passport_number),
            ("passport_valid_until", passport_valid_until),
            ("hobbies", hobbies),
        )
        if value.strip()
    }

    def normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.casefold())

    def remove_json_duplicates(value: dict) -> dict:
        known_text = {
            "passport_number": passport_number,
            "passport_valid_until": passport_valid_until,
            "hobbies": hobbies,
        }
        return {
            key: item for key, item in value.items()
            if not (
                (field := aliases.get(normalize(key)))
                and isinstance(item, str)
                and known_text[field].strip()
                and item.strip().casefold() == known_text[field].strip().casefold()
            )
        }

    lines = details.splitlines()
    kept = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if re.fullmatch(r"```(?:json)?\s*", line.strip(), re.IGNORECASE):
            end = index + 1
            while end < len(lines) and lines[end].strip() != "```":
                end += 1
            if end < len(lines):
                block = "\n".join(lines[index + 1:end])
                try:
                    value = json.loads(block)
                except json.JSONDecodeError:
                    value = None
                if isinstance(value, dict):
                    remaining = remove_json_duplicates(value)
                    if remaining != value:
                        if remaining:
                            kept.extend((line, json.dumps(remaining, ensure_ascii=False, indent=2), lines[end]))
                    else:
                        kept.extend(lines[index:end + 1])
                    index = end + 1
                    continue
        if line.lstrip().startswith("{"):
            block = "\n".join(lines[index:]).lstrip()
            try:
                value, end_pos = json.JSONDecoder().raw_decode(block)
            except json.JSONDecodeError:
                value = None
            if isinstance(value, dict):
                consumed = block[:end_pos]
                count = consumed.count("\n") + 1
                trailing = block[end_pos:].split("\n", 1)[0]
                if not trailing.strip():
                    remaining = remove_json_duplicates(value)
                    if remaining != value:
                        if remaining:
                            kept.append(json.dumps(remaining, ensure_ascii=False, indent=2 if count > 1 else None))
                    else:
                        kept.extend(lines[index:index + count])
                    index += count
                    continue
        cleaned = re.sub(r"[*_`]", "", line).strip().lstrip("•-").strip()
        if not cleaned:
            kept.append(line)
            index += 1
            continue
        if ":" in cleaned:
            label, value = cleaned.split(":", 1)
            field = aliases.get(normalize(label))
            if field and normalize(value) == known_values.get(field):
                index += 1
                continue
        normalized = normalize(cleaned)
        if normalized and normalized in known_values.values():
            index += 1
            continue
        field = aliases.get(normalized)
        if field and known_values.get(field):
            next_index = index + 1
            while next_index < len(lines) and not lines[next_index].strip():
                next_index += 1
            if next_index < len(lines) and normalize(lines[next_index]) == known_values[field]:
                index = next_index + 1
                continue
        kept.append(line)
        index += 1
    return "\n".join(kept).strip()


class Resume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", max_length=500)
    headline: str = Field(default="", max_length=500)
    contact: str = Field(default="", max_length=2000)
    email: str = Field(default="", max_length=500)
    phone: str = Field(default="", max_length=500)
    location: str = Field(default="", max_length=500)
    linkedin: str = Field(default="", max_length=500)
    github: str = Field(default="", max_length=500)
    website: str = Field(default="", max_length=500)
    passport_number: str = Field(default="", max_length=500)
    passport_valid_until: str = Field(default="", max_length=500)
    summary: str = Field(default="", max_length=10000)
    experience: str = Field(default="", max_length=20000)
    experience_entries: list[ExperienceEntry] = Field(default_factory=list, max_length=30)
    education: str = Field(default="", max_length=10000)
    education_entries: list[EducationEntry] = Field(default_factory=list, max_length=30)
    skills: str = Field(default="", max_length=10000)
    skill_groups: list[SkillGroup] = Field(default_factory=list, max_length=30)
    projects: str = Field(default="", max_length=10000)
    leadership: str = Field(default="", max_length=10000)
    awards: str = Field(default="", max_length=10000)
    certifications: str = Field(default="", max_length=10000)
    hobbies: str = Field(default="", max_length=10000)
    personal_details: str = Field(default="", max_length=10000)
    additional: str = Field(default="", max_length=10000)

    @model_validator(mode="after")
    def remove_repeated_personal_details(self):
        self.personal_details = remove_repeated_personal_details(
            self.personal_details, self.passport_number, self.passport_valid_until, self.hobbies
        )
        return self


TemplateId = Literal["classic", "altacv", "latexcv_classic", "latexcv_modern", "latexcv_two_column"]


class ExportRequest(BaseModel):
    resume: Resume
    format: Literal["pdf", "docx"]
    template: TemplateId = "classic"


class RecommendationRequest(BaseModel):
    resume: Resume
    messages: list[Message] = Field(max_length=100)
    model: str = Field(default=DEFAULT_MODEL, min_length=1, max_length=200)


class Recommendation(BaseModel):
    template: TemplateId
    reason: str = Field(min_length=1, max_length=500)


class ResumeUpdateRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=100)
    resume: Resume
    model: str = Field(default=DEFAULT_MODEL, min_length=1, max_length=200)


class ResumeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    generate_resume: bool = Field(strict=True)
    name: str | None = Field(default=None, max_length=500)
    headline: str | None = Field(default=None, max_length=500)
    contact: str | None = Field(default=None, max_length=2000)
    email: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=500)
    linkedin: str | None = Field(default=None, max_length=500)
    github: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=500)
    passport_number: str | None = Field(default=None, max_length=500)
    passport_valid_until: str | None = Field(default=None, max_length=500)
    summary: str | None = Field(default=None, max_length=10000)
    experience: str | None = Field(default=None, max_length=20000)
    experience_entries: list[ExperienceEntry] | None = Field(default=None, max_length=30)
    education: str | None = Field(default=None, max_length=10000)
    education_entries: list[EducationEntry] | None = Field(default=None, max_length=30)
    skills: str | None = Field(default=None, max_length=10000)
    skill_groups: list[SkillGroup] | None = Field(default=None, max_length=30)
    projects: str | None = Field(default=None, max_length=10000)
    leadership: str | None = Field(default=None, max_length=10000)
    awards: str | None = Field(default=None, max_length=10000)
    certifications: str | None = Field(default=None, max_length=10000)
    hobbies: str | None = Field(default=None, max_length=10000)
    personal_details: str | None = Field(default=None, max_length=10000)
    additional: str | None = Field(default=None, max_length=10000)


INTERVIEW_PROMPT = """You are a thoughtful resume-writing assistant conducting an interview.
Ask concise, relevant follow-up questions to gather the user's name, contact details, desired
role, email, phone, location, LinkedIn and GitHub, work experience (each role, employer,
client, dates, location, responsibilities, measurable achievements, and technologies),
education (qualification, institution and year), grouped skills, projects, leadership,
awards, certifications, hobbies and any other details the user wants included. The user may ask
questions or provide information in any form; respond naturally and helpfully rather than
restricting them to a predefined list of fields. Ask at most two follow-up questions at a time.
Ask the user to state the details in their answers instead of simply answering yes or no.
Adapt to the user's answers; skip irrelevant sections and allow them to say they don't know or
want to skip. Never invent facts or assume achievements. When you have enough information,
ask if they want to generate their resume, and tell them they can request it at any time.
Passport details are optional and sensitive. Ask whether the user wishes to include passport
details, explain they are sensitive, and only ask for the number or expiration date if they opt in.
Do not request other government IDs, date of birth or a full street address.
Return JSON with message and generate_resume. Do not claim that changes were applied to an
existing draft. Set generate_resume true only when the latest user message explicitly requests
resume generation or confirms your preceding offer to generate it.
If the user asks to generate now, immediately set generate_resume true even if information is
missing. Do not ask further questions first; the user can edit missing details later.
Do not treat an answer to a factual question, a request to continue the interview, or the mere
presence of sufficient information as permission to generate. If generate_resume is true, keep
message short and do not claim the resume has already been created. Otherwise answer the user's
latest message naturally and ask a relevant follow-up when useful.
Examples: "Please generate my resume now" -> generate_resume true;
after "Would you like me to generate your resume?", "Yes, please" -> true;
"Not yet, I want to add more experience" -> false; "I know Python" -> false."""

DRAFT_PROMPT = """Create a professional, ATS-friendly resume from the user's statements.
Return only the requested JSON, including every field. Place the user's name in name. Keep each fact in the appropriate
section rather than placing education or experience in additional. Use only facts explicitly
provided by the user; never invent
names, dates, employers, degrees, metrics, skills or achievements. Do not treat assistant
suggestions or questions as facts. Leave unknown strings empty and unknown lists empty. Do not use placeholders.
Never supply example email addresses or phone numbers. Fill email, phone, location, linkedin,
github and website separately when provided. Use contact only for other contact information.
Put each employer, client, role, dates, location, achievements and technologies in experience_entries.
Put each qualification, institution and year in education_entries. Put grouped skills in skill_groups.
Leave experience, education and skills empty if the same information is in their structured entries.
Keep each entry complete and concise. Never repeat words or list unmentioned technologies.
Put leadership, awards and certifications
in their dedicated fields. Put explicitly provided passport number, passport expiration and
hobbies in passport_number, passport_valid_until and hobbies respectively. Never invent them.
Put any other explicitly provided personal information in personal_details, preserving its meaning.
Do not repeat passport details or hobbies in personal_details when they are stored in their dedicated fields.
If a degree was not specified, do not name a degree.
Write concise, polished wording without changing the meaning. Put each item on a separate line
in the section strings. Use plain text, not Markdown. Contact may contain email, phone, location
and links if supplied. Include a headline only if supported by the user's stated target or role."""

async def ollama_chat(model: str, messages: list[dict], schema: dict | None = None) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    if schema is not None:
        payload["format"] = schema
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        content = data["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama returned an empty response")
        return content
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "Ollama timed out. Try again or choose a smaller model.") from exc
    except httpx.HTTPStatusError as exc:
        logger.warning("Ollama returned HTTP %s", exc.response.status_code)
        raise HTTPException(502, "Ollama could not run the selected model. Check that it is installed.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(503, "Cannot connect to Ollama. Start Ollama and try again.") from exc
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("Invalid Ollama response: %s", exc)
        raise HTTPException(502, "Ollama returned an invalid response. Please try again.") from exc


@app.get("/api/config")
def config():
    return {"default_model": DEFAULT_MODEL}


@app.post("/api/import-pdf")
async def import_pdf(file: UploadFile):
    try:
        content = await file.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(413, "PDF must be 10 MB or smaller.")
        if not content.startswith(b"%PDF-"):
            raise HTTPException(422, "Select a valid PDF file.")
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise HTTPException(422, "Password-protected PDFs are not supported.")
        if len(reader.pages) > 20:
            raise HTTPException(422, "PDF must have at most 20 pages.")
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if not text:
            raise HTTPException(422, "No readable text found. Scanned PDFs require OCR, which is not supported.")
        if len(text) > 11500:
            raise HTTPException(422, "The extracted PDF text is too long. Use a shorter PDF.")
        return {"text": text}
    except (PdfReadError, ValueError, OSError) as exc:
        raise HTTPException(422, "Could not read the PDF. Check that the file is valid.") from exc
    finally:
        await file.close()


@app.post("/api/interview")
async def interview(request: InterviewRequest):
    if request.messages[-1].role != "user":
        raise HTTPException(422, "The latest interview message must be from the user.")
    messages = [{"role": "system", "content": INTERVIEW_PROMPT + f"\nDraft exists: {request.has_draft}."}]
    messages.extend(message.model_dump() for message in request.messages)
    schema = InterviewResponse.model_json_schema()
    schema["required"] = list(schema["properties"])
    content = await ollama_chat(request.model, messages, schema)
    try:
        return InterviewResponse.model_validate_json(content)
    except ValidationError as exc:
        logger.warning("Ollama returned an invalid interview response")
        raise HTTPException(502, "Ollama returned an invalid interview response. Please send your message again.") from exc


@app.post("/api/resume-update")
async def resume_update(request: ResumeUpdateRequest):
    if request.messages[-1].role != "user":
        raise HTTPException(422, "The latest update message must be from the user.")
    prompt = (
        "You are a helpful resume assistant. The user may ask for any kind of resume change or "
        "ask a general question; do not limit requests to a predefined set of personal fields. "
        "Use the conversation for context and make only changes explicitly requested in the latest "
        "user message. Return null for every unchanged field. Use an empty string only when the "
        "user explicitly asks to remove a string value. Preserve all unrelated information. For "
        "list fields, preserve existing entries and change only what was requested. Store arbitrary "
        "personal information such as a favorite book in personal_details. Never invent facts. "
        "Do not duplicate passport details or hobbies in personal_details when they appear in their dedicated fields. "
        "Use plain text in resume fields, not JSON or Markdown. "
        "Copy passport details exactly from the user's message. Set generate_resume true only if "
        "the latest message explicitly requests generating or regenerating the resume; otherwise "
        "false. If no resume change or generation is requested, answer the user's question helpfully "
        "in message and leave all change fields null. Return JSON only."
    )
    messages = [{"role": "system", "content": prompt}]
    messages.extend(message.model_dump() for message in request.messages)
    messages[-1]["content"] += f"\n\nCurrent resume JSON:\n{request.resume.model_dump_json()}"
    schema = ResumeUpdate.model_json_schema()
    schema["required"] = list(schema["properties"])
    content = await ollama_chat(request.model, messages, schema)
    try:
        update = ResumeUpdate.model_validate_json(content)
    except ValidationError as exc:
        logger.warning("Ollama returned an invalid resume update")
        raise HTTPException(502, "Ollama returned an invalid update. Please try again.") from exc
    current = request.resume.model_dump()
    updates = update.model_dump(exclude={"message", "generate_resume"}, exclude_none=True)
    changes = {key: value for key, value in updates.items() if value != current[key]}
    updated_resume = Resume.model_validate({**current, **changes}).model_dump()
    changes = {key: value for key, value in updated_resume.items() if value != current[key]}
    if not changes:
        return {"changes": {}, "resume": updated_resume, "message": update.message, "generate_resume": update.generate_resume}
    for key in ("passport_number", "passport_valid_until"):
        value = changes.get(key)
        if value and value.casefold() not in request.messages[-1].content.casefold():
            raise HTTPException(502, "The passport details could not be verified against your message. Please try again or use Edit.")
    return {"changes": changes, "resume": updated_resume, "message": update.message, "generate_resume": update.generate_resume}


@app.post("/api/draft")
async def draft(request: InterviewRequest):
    if not any(message.role == "user" for message in request.messages):
        raise HTTPException(422, "Add your information before creating a draft.")
    statements = "\n\n".join(message.content for message in request.messages if message.role == "user")
    messages = [
        {"role": "system", "content": DRAFT_PROMPT},
        {"role": "user", "content": f"Create the resume JSON using only these statements:\n\n{statements}"},
    ]
    schema = Resume.model_json_schema()
    schema["required"] = list(schema["properties"])
    for definition in (schema, *schema.get("$defs", {}).values()):
        if "properties" in definition:
            definition["required"] = list(definition["properties"])
            for field in definition["properties"].values():
                field.pop("default", None)
    content = await ollama_chat(request.model, messages, schema)
    try:
        return Resume.model_validate_json(content)
    except ValidationError as exc:
        logger.warning("Ollama returned a resume that failed validation")
        raise HTTPException(502, "Ollama returned an invalid resume. Please try generating the draft again.") from exc


@app.post("/api/recommend-template")
async def recommend_template(request: RecommendationRequest):
    if not has_content(request.resume):
        raise HTTPException(422, "Create a resume draft before requesting a recommendation.")
    statements = "\n\n".join(m.content for m in request.messages if m.role == "user")
    prompt = (
        "Recommend one resume template based on the user's target and explicitly stated style "
        "preferences. Do not infer sensitive traits. Available templates: classic: simple single "
        "column; altacv: two columns, burgundy headings; latexcv_classic: single column, "
        "blue centered headings; latexcv_modern: single column, orange heading bars; "
        "latexcv_two_column: two columns with dark heading bars. "
        "Give a short practical reason; do not claim guaranteed ATS compatibility. "
        "Return only JSON with template and reason."
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"User statements:\n{statements}\n\nResume draft:\n{request.resume.model_dump_json()}"},
    ]
    content = await ollama_chat(request.model, messages, Recommendation.model_json_schema())
    try:
        return Recommendation.model_validate_json(content)
    except ValidationError as exc:
        logger.warning("Ollama returned an invalid template recommendation")
        raise HTTPException(502, "Ollama returned an invalid recommendation. Try again or choose a template manually.") from exc


def build_docx(resume: Resume, template: str = "classic") -> io.BytesIO:
    document = Document()
    normal = document.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(10)
    for section in document.sections:
        section.top_margin = section.bottom_margin = Inches(0.7)
    if resume.name:
        document.add_heading(resume.name, 0)
    if resume.headline:
        document.add_paragraph(resume.headline)
    for label, value in contact_lines(resume):
        paragraph = document.add_paragraph()
        if label:
            paragraph.add_run(f"{label}: ").bold = True
        paragraph.add_run(value)
    footer = document.sections[0].footer.paragraphs[0]
    footer.add_run(f"{resume.name} — " if resume.name else "")
    footer.add_run("Page ")
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    footer.add_run(" of ")
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "NUMPAGES")
    footer._p.append(field)
    if template in ("altacv", "latexcv_two_column"):
        table = document.add_table(rows=1, cols=2)
        table.autofit = False
        table.columns[0].width = Inches(4)
        table.columns[1].width = Inches(2.6)
        table.rows[0].cells[0].width = Inches(4)
        table.rows[0].cells[1].width = Inches(2.6)
        groups = [
            [("summary", "Professional Summary"), ("experience", "Experience"), ("projects", "Projects")],
            [("skills", "Skills"), ("education", "Education"), ("leadership", "Leadership"),
             ("awards", "Awards"), ("personal_information", "Personal Information"),
             ("certifications", "Certifications"), ("additional", "Additional Information")],
        ]
        for cell, group in zip(table.rows[0].cells, groups):
            for key, title in group:
                value = section_text(resume, key)
                if value:
                    cell.add_paragraph(title, style="Heading 1")
                    if key == "personal_information":
                        add_personal_docx(cell, resume)
                    elif key == "experience":
                        add_experience_docx(cell, resume)
                    else:
                        for line in value.splitlines():
                            if line.strip():
                                cell.add_paragraph(line.strip())
    else:
        if template in ("latexcv_classic", "latexcv_modern"):
            from docx.shared import RGBColor
            heading_style = document.styles["Heading 1"]
            heading_style.font.color.rgb = RGBColor.from_string(
                "0096FF" if template == "latexcv_classic" else "E08000"
            )
        for key, title in SECTIONS:
            value = section_text(resume, key)
            if value:
                document.add_heading(title, level=1)
                if key == "personal_information":
                    add_personal_docx(document, resume)
                elif key == "experience":
                    add_experience_docx(document, resume)
                else:
                    for line in value.splitlines():
                        if line.strip():
                            document.add_paragraph(line.strip())
    output = io.BytesIO()
    document.save(output)
    output.seek(0)
    return output


def add_personal_docx(container, resume: Resume):
    for label, value in personal_lines(resume):
        paragraph = container.add_paragraph()
        if label:
            paragraph.add_run(f"{label}: ").bold = True
        paragraph.add_run(value)


def add_experience_docx(container, resume: Resume):
    for line, bold_prefix in experience_lines(resume):
        paragraph = container.add_paragraph()
        if not line:
            paragraph.paragraph_format.line_spacing = Pt(14)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
        elif bold_prefix:
            paragraph.add_run(bold_prefix).bold = True
            paragraph.add_run(line[len(bold_prefix):])
        else:
            paragraph.add_run(line)


def pdf_font() -> str:
    paths = [
        os.environ.get("RESUME_PDF_FONT", ""),
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in paths:
        if path and Path(path).is_file():
            regular_path = Path(path)
            bold_candidates = (
                regular_path.with_name(f"{regular_path.stem}-Bold{regular_path.suffix}"),
                regular_path.with_name(f"{regular_path.stem} Bold{regular_path.suffix}"),
            )
            if regular_path.name == "Arial Unicode.ttf":
                bold_candidates += (regular_path.with_name("Arial Bold.ttf"),)
            bold_path = next((candidate for candidate in bold_candidates if candidate.is_file()), None)
            if "ResumeUnicode" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("ResumeUnicode", str(regular_path)))
            if bold_path and "ResumeUnicode-Bold" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("ResumeUnicode-Bold", str(bold_path)))
            bold_font = "ResumeUnicode-Bold" if bold_path else "ResumeUnicode"
            pdfmetrics.registerFontFamily(
                "ResumeUnicode", normal="ResumeUnicode", bold=bold_font,
                italic="ResumeUnicode", boldItalic=bold_font,
            )
            return "ResumeUnicode"
    raise HTTPException(500, "No Unicode PDF font found. Set RESUME_PDF_FONT to a TrueType font file.")


def build_pdf(resume: Resume) -> io.BytesIO:
    font = pdf_font()
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=(8.5 * inch, 11 * inch),
                                 leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                                 topMargin=0.65 * inch, bottomMargin=0.65 * inch)
    styles = getSampleStyleSheet()
    name_style = ParagraphStyle("ResumeName", parent=styles["Normal"], fontName=font,
                                fontSize=20, leading=25, alignment=TA_CENTER)
    centered = ParagraphStyle("ResumeContact", parent=styles["Normal"], fontName=font,
                              fontSize=10, leading=14, alignment=TA_CENTER)
    heading = ParagraphStyle("ResumeHeading", parent=styles["Normal"], fontName=font,
                             fontSize=12, leading=16, textColor=colors.HexColor("#315b54"),
                             spaceBefore=12, spaceAfter=5, keepWithNext=True)
    body = ParagraphStyle("ResumeBody", parent=styles["Normal"], fontName=font,
                          fontSize=10, leading=14, spaceAfter=3, splitLongWords=True)
    story = []
    for text, style in ((resume.name, name_style), (resume.headline, centered)):
        if text.strip():
            story.append(Paragraph(escape(text).replace("\n", "<br/>"), style))
    for label, value in contact_lines(resume):
        prefix = f'<font name="Helvetica-Bold">{escape(label)}:</font> ' if label else ""
        story.append(Paragraph(prefix + escape(value).replace("\n", "<br/>"), centered))
    story.append(Spacer(1, 8))
    for key, title in SECTIONS:
        value = section_text(resume, key)
        if value:
            story.append(Paragraph(title, heading))
            if key == "personal_information":
                for label, detail in personal_lines(resume):
                    prefix = f'<font name="Helvetica-Bold">{escape(label)}:</font> ' if label else ""
                    story.append(Paragraph(prefix + escape(detail).replace("\n", "<br/>"), body))
            elif key == "experience":
                for line, bold_prefix in experience_lines(resume):
                    if not line:
                        story.append(Spacer(1, body.leading))
                        continue
                    text = escape(line)
                    if bold_prefix:
                        escaped_prefix = escape(bold_prefix)
                        text = f"<b>{escaped_prefix}</b>{escape(line[len(bold_prefix):])}"
                    story.append(Paragraph(text.replace("\n", "<br/>"), body))
            else:
                for line in value.splitlines():
                    if line.strip():
                        story.append(Paragraph(escape(line.strip()), body))
    class NumberedCanvas(Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.page_states = []

        def showPage(self):
            self.page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            count = len(self.page_states)
            for state in self.page_states:
                self.__dict__.update(state)
                self.setFont(font, 8)
                self.drawString(document.leftMargin, 0.35 * inch, resume.name)
                self.drawRightString(8.5 * inch - document.rightMargin, 0.35 * inch, f"Page {self._pageNumber} of {count}")
                super().showPage()
            super().save()

    document.build(story, canvasmaker=NumberedCanvas)
    output.seek(0)
    return output


@app.post("/api/export")
def export(request: ExportRequest):
    if not has_content(request.resume):
        raise HTTPException(422, "Add resume content before exporting.")
    if request.format == "pdf":
        if request.template == "altacv":
            stream = build_altacv_pdf(request.resume)
        elif request.template in ("latexcv_classic", "latexcv_modern", "latexcv_two_column"):
            stream = build_latexcv_pdf(request.resume, request.template)
        else:
            stream = build_pdf(request.resume)
        media_type = "application/pdf"
    else:
        stream = build_docx(request.resume, request.template)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return StreamingResponse(stream, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="resume.{request.format}"'
    })
