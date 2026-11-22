import io
import logging
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from backend.resume_content import contact_lines, experience_lines, personal_lines, section_text

logger = logging.getLogger(__name__)
CLASS_FILE = Path(__file__).parent / "vendor" / "altacv" / "altacv.cls"

TEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "%": r"\%",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def tex_text(text: str) -> str:
    return "".join(TEX_ESCAPES.get(character, character) for character in text)


def section(title: str, content: str) -> str:
    if not content.strip():
        return ""
    lines = "\n".join(
        tex_text(line.strip()) + r"\par" for line in content.splitlines() if line.strip()
    )
    return f"\\cvsection{{{title}}}\n{lines}\n"


def resume_section(resume, key: str, title: str) -> str:
    if key == "experience":
        lines = "\n".join(
            ((r"\textbf{" + tex_text(bold_prefix) + "}" + tex_text(line[len(bold_prefix):])
              if bold_prefix else tex_text(line)) + r"\par" if line else r"\vspace{\baselineskip}")
            for line, bold_prefix in experience_lines(resume)
        )
        return f"\\cvsection{{{title}}}\n{lines}\n" if lines else ""
    if key != "personal_information":
        return section(title, section_text(resume, key))
    lines = personal_lines(resume)
    if not lines:
        return ""
    content = "\n".join(
        (r"\textbf{" + tex_text(label) + r":} " if label else "")
        + tex_text(value).replace("\n", r"\par ") + r"\par"
        for label, value in lines
    )
    return f"\\cvsection{{{title}}}\n{content}\n"


def tex_contact(resume) -> str:
    return r" \textbar{} ".join(
        (r"\textbf{" + tex_text(label) + r":} " if label else "") + tex_text(value)
        for label, value in contact_lines(resume)
    )


def tex_footer(resume) -> str:
    name = tex_text(resume.name)
    return (r"\renewcommand{\thepage}{\arabic{page}}\pagestyle{fancy}\fancyhf{}\renewcommand{\headrulewidth}{0pt}"
            r"\fancyfoot[L]{" + name + r"}\fancyfoot[R]{Page \arabic{page} of \pageref{LastPage}}" "\n")


def compile_tex(source: str, name: str, class_file: Path | None = None) -> io.BytesIO:
    compiler = shutil.which("tectonic")
    if not compiler:
        raise HTTPException(503, f"{name} requires Tectonic. Install it and restart the backend.")
    if class_file is not None and not class_file.is_file():
        raise HTTPException(500, f"The {name} template class is missing.")
    try:
        with tempfile.TemporaryDirectory(prefix="resume-genie-") as directory:
            path = Path(directory)
            if class_file is not None:
                shutil.copyfile(class_file, path / class_file.name)
            (path / "resume.tex").write_text(source, encoding="utf-8")
            result = subprocess.run(
                [compiler, "--untrusted", "--outdir", directory, "resume.tex"],
                cwd=directory, capture_output=True, timeout=600, check=False,
            )
            if result.returncode != 0:
                logger.error("%s compilation failed (exit %s)", name, result.returncode)
                raise HTTPException(500, f"{name} PDF compilation failed. Check the Tectonic installation and its packages.")
            return io.BytesIO((path / "resume.pdf").read_bytes())
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, f"{name} PDF generation timed out. Check your internet connection and try again.") from exc
    except OSError as exc:
        logger.exception("Could not run %s compiler", name)
        raise HTTPException(500, f"Could not run the {name} PDF compiler.") from exc


def build_altacv_pdf(resume) -> io.BytesIO:
    left = "".join(resume_section(resume, key, title) for key, title in (
        ("summary", "Professional Summary"), ("experience", "Experience"), ("projects", "Projects")
    ))
    right = "".join(resume_section(resume, key, title) for key, title in (
        ("skills", "Skills"), ("education", "Education"), ("leadership", "Leadership"),
        ("awards", "Awards"), ("personal_information", "Personal Information"),
        ("certifications", "Certifications"), ("additional", "Additional Information")
    ))
    contact = tex_contact(resume)
    source = (
        # pdfx normally obtains this through shell escape, which is disabled for safety.
        "\\edef\\pdfcreationdate{\\string D:" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "+00'00'}\n"
        r"\documentclass[10pt,a4paper]{altacv}" "\n"
        r"\usepackage{paracol}" "\n"
        r"\usepackage{fancyhdr}" "\n"
        r"\usepackage{lastpage}" "\n"
        r"\geometry{left=1.5cm,right=1.5cm,top=1.5cm,bottom=1.5cm,columnsep=1cm}" "\n"
        r"\definecolor{DarkRed}{HTML}{450808}" "\n"
        r"\definecolor{AccentRed}{HTML}{8F0D0D}" "\n"
        r"\definecolor{Gold}{HTML}{E7D192}" "\n"
        r"\colorlet{heading}{DarkRed}\colorlet{headingrule}{Gold}\colorlet{accent}{AccentRed}" "\n"
        r"\colorlet{tagline}{AccentRed}" "\n"
        r"\renewcommand{\namefont}{\Huge\rmfamily\bfseries}" "\n"
        r"\renewcommand{\cvsectionfont}{\Large\rmfamily\bfseries}" "\n"
        r"\begin{document}" "\n"
        + tex_footer(resume)
        + "\\name{" + tex_text(resume.name) + "}\n"
        + "\\tagline{" + tex_text(resume.headline) + "}\n"
        + "\\personalinfo{" + contact + "}\n"
        + r"\makecvheader" "\n"
        + r"\columnratio{0.6}" "\n"
        + r"\begin{paracol}{2}" "\n"
        + left + r"\switchcolumn" "\n" + right
        + r"\end{paracol}" "\n" + r"\end{document}" "\n"
    )
    return compile_tex(source, "AltaCV", CLASS_FILE)
