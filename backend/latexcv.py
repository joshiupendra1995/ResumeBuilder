from pathlib import Path

from fastapi import HTTPException

from backend.altacv import compile_tex, resume_section, tex_text, tex_contact, tex_footer
from backend.resume_content import SECTIONS

TEMPLATES = {
    "latexcv_classic": "classic.tex",
    "latexcv_modern": "modern.tex",
    "latexcv_two_column": "two_column.tex",
}
TEMPLATE_DIR = Path(__file__).parent / "vendor" / "latexcv"


def build_latexcv_pdf(resume, template: str):
    path = TEMPLATE_DIR / TEMPLATES[template]
    try:
        original = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(500, "The selected LaTeX CV template is missing.") from exc
    preamble, separator, _ = original.partition(r"\begin{document}")
    if not separator:
        raise HTTPException(500, "The selected LaTeX CV template is invalid.")
    preamble += "\n" + r"\usepackage{lastpage}" "\n" + r"\geometry{bottom=1.8cm,footskip=0.7cm}" + "\n"
    header = "\n".join(
        r"\begin{center}" + style + tex_text(value.strip()) + r"\end{center}"
        for value, style in (
            (resume.name, r"\Huge\bfseries "),
            (resume.headline, r"\large "),
        )
        if value.strip()
    )
    if tex_contact(resume):
        header += "\n" + r"\begin{center}\small " + tex_contact(resume) + r"\end{center}"
    if template == "latexcv_two_column":
        # Tectonic's bundled Roboto lacks the condensed thin face used by this preamble.
        preamble = preamble.replace(r"\usepackage[thin]{roboto}", r"\usepackage[default]{raleway}")
        left = ("summary", "experience", "projects")
        right = ("skills", "education", "leadership", "awards", "personal_information", "certifications", "additional")
        titles = dict(SECTIONS)
        def render_group(group):
            return "".join(resume_section(resume, key, titles[key]) for key in group)
        preamble += "\n" + r"\usepackage{paracol}" + "\n"
        body = (r"\columnratio{0.55}" "\n" r"\begin{paracol}{2}" "\n"
                + render_group(left) + r"\switchcolumn" "\n"
                + render_group(right) + r"\end{paracol}" "\n")
    else:
        body = "".join(resume_section(resume, key, title) for key, title in SECTIONS)
    return compile_tex(preamble + separator + "\n" + tex_footer(resume) + header + "\n" + body + r"\end{document}", "LaTeX CV")
