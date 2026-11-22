import re

CONTACT_FIELDS = (
    ("email", "Email"), ("phone", "Phone"), ("location", "Location"),
    ("linkedin", "LinkedIn"), ("github", "GitHub"), ("website", "Website"),
)
PERSONAL_FIELDS = (
    ("passport_number", "Passport number"),
    ("passport_valid_until", "Passport valid until"),
    ("hobbies", "Hobbies"),
)
SECTIONS = (
    ("summary", "Professional Summary"), ("experience", "Experience"),
    ("education", "Education"), ("skills", "Skills"), ("projects", "Projects"),
    ("leadership", "Leadership"), ("awards", "Awards"),
    ("personal_information", "Personal Information"), ("certifications", "Certifications"),
    ("additional", "Additional Information"),
)


def contact_lines(resume):
    result = [(label, getattr(resume, key).strip()) for key, label in CONTACT_FIELDS if getattr(resume, key).strip()]
    for line in resume.contact.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(Email|Phone|Location|LinkedIn|GitHub|Website):\s*(.*)$", line, re.IGNORECASE)
        if match:
            label, value = match.groups()
            if getattr(resume, label.lower()).strip().casefold() != value.strip().casefold():
                result.append((label, value))
        else:
            result.append(("", line))
    return result


def section_text(resume, key):
    if key == "personal_information":
        return "\n".join(f"{label}: {value}" if label else value for label, value in personal_lines(resume))
    if key == "experience":
        return "\n".join(line for line, _ in experience_lines(resume))
    text = getattr(resume, key).strip()
    extra = []
    if key == "education":
        for entry in resume.education_entries:
            line = " — ".join(x for x in (entry.qualification.strip(), entry.institution.strip(), entry.year.strip()) if x)
            if line:
                extra.append(line)
    elif key == "skills":
        for entry in resume.skill_groups:
            category, skills = entry.category.strip(), entry.skills.strip()
            if category or skills:
                extra.append(f"{category}: {skills}" if category and skills else category or skills)
    return "\n".join(x for x in (text, "\n".join(extra)) if x)


def experience_lines(resume):
    raw_lines = [line.strip() for line in resume.experience.splitlines()]
    lines = []
    for index, line in enumerate(raw_lines):
        if not line:
            if lines and lines[-1][0]:
                lines.append(("", None))
            continue
        is_heading = (
            re.match(r"^.+\s+[—–-]\s+\S", line)
            and re.match(
                r"^(?:client\s*:|(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b|(?:19|20)\d{2}\b|\d{1,2}[/-]\d)",
                next((value for value in raw_lines[index + 1:] if value), ""), re.IGNORECASE,
            )
        )
        if is_heading and lines and lines[-1][0]:
            lines.append(("", None))
        lines.append((line, None))
    if lines and not lines[-1][0]:
        lines.pop()
    has_entry = bool(lines)
    for entry in resume.experience_entries:
        title = " — ".join(x for x in (entry.role.strip(), entry.employer.strip()) if x)
        details = " | ".join(x for x in (entry.dates.strip(), entry.location.strip()) if x)
        technologies = f"Technologies: {entry.technologies.strip()}" if entry.technologies.strip() else ""
        entry_lines = [
            (line, bold_prefix)
            for line, bold_prefix in (
                (title, title),
                (f"Client: {entry.client.strip()}" if entry.client.strip() else "", None),
                (details, None),
                (entry.achievements.strip(), None),
                (technologies, "Technologies:" if technologies else None),
            )
            if line
        ]
        if entry_lines:
            if has_entry:
                lines.append(("", None))
            lines.extend(entry_lines)
            has_entry = True
    return lines


def personal_lines(resume):
    lines = [(label, getattr(resume, key).strip()) for key, label in PERSONAL_FIELDS if getattr(resume, key).strip()]
    details = resume.personal_details.strip()
    if details:
        lines.append(("", details))
    return lines


def has_content(resume):
    return (any(value.strip() for value in resume.model_dump().values() if isinstance(value, str))
            or any(section_text(resume, key) for key in ("experience", "education", "skills")))
