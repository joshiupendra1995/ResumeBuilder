import io
import json
import unittest
from unittest.mock import AsyncMock, patch

from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from backend.altacv import tex_text
from backend.app import app


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.messages = [
            {"role": "assistant", "content": "What is your name?"},
            {"role": "user", "content": "My name is Ada."},
        ]

    def test_interview_forwards_conversation(self):
        with patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value='{"message":"What is your experience?","generate_resume":false}') as chat:
            response = self.client.post("/api/interview", json={"messages": self.messages, "model": "qwen2.5:14b"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "What is your experience?", "generate_resume": False})
        self.assertEqual(chat.await_args.args[1][1:], self.messages)
        self.assertIn("generate_resume", chat.await_args.args[2]["properties"])

    def test_interview_accepts_user_confirmation(self):
        messages = self.messages + [
            {"role": "assistant", "content": "Would you like me to generate your resume?"},
            {"role": "user", "content": "Yes, please."},
        ]
        with patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value='{"message":"Let’s generate it.","generate_resume":true}'):
            response = self.client.post("/api/interview", json={"messages": messages})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["generate_resume"])

    def test_invalid_interview_output_is_reported(self):
        for content in ('not json', '{"message":"OK","generate_resume":"yes"}', '{"message":"OK"}'):
            with self.subTest(content=content), patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value=content):
                response = self.client.post("/api/interview", json={"messages": self.messages})
            self.assertEqual(response.status_code, 502)

    def test_interview_requires_user_last_message(self):
        response = self.client.post("/api/interview", json={"messages": [self.messages[0]]})
        self.assertEqual(response.status_code, 422)

    def test_draft_validates_structured_output(self):
        with patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value='{"name":"Ada","skills":"Python"}') as chat:
            response = self.client.post("/api/draft", json={"messages": self.messages})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Ada")
        self.assertEqual(response.json()["skills"], "Python")
        schema = chat.await_args.args[2]
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        self.assertIn("personal_details", schema["properties"])
        draft_messages = chat.await_args.args[1]
        self.assertNotIn("What is your name?", str(draft_messages))
        self.assertIn("My name is Ada.", draft_messages[1]["content"])

    def test_invalid_draft_is_reported(self):
        with patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value="not json"):
            response = self.client.post("/api/draft", json={"messages": self.messages})
        self.assertEqual(response.status_code, 502)

    def test_resume_updates_any_fields_and_validates_passport_details(self):
        response_data = '{"message":"Updated.","generate_resume":false,"passport_number":"AB123456","passport_valid_until":"2030-10-20","hobbies":null}'
        payload = {
            "messages": [{"role": "user", "content": "Passport AB123456 expires 2030-10-20"}],
            "resume": {"hobbies": "Chess", "name": "Ada"},
        }
        with patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value=response_data) as chat:
            response = self.client.post("/api/resume-update", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["changes"], {"passport_number": "AB123456", "passport_valid_until": "2030-10-20"})
        self.assertIn("Chess", chat.await_args.args[1][1]["content"])
        self.assertIn("personal_details", chat.await_args.args[2]["properties"])
        for result in ('{"message":"Updated.","generate_resume":false,"passport_number":"FAKE"}',
                       '{"message":"Updated.","generate_resume":false,"passport_valid_until":"2050"}'):
            with self.subTest(result=result), patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value=result):
                response = self.client.post("/api/resume-update", json=payload)
            self.assertEqual(response.status_code, 502)
        with patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value='{"message":"I can help with that.","generate_resume":false}'):
            response = self.client.post("/api/resume-update", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "I can help with that.")
        with patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value='{"message":"Done.","generate_resume":false,"hobbies":"Chess"}'):
            response = self.client.post("/api/resume-update", json=payload)
        self.assertEqual(response.json()["changes"], {})
        removal = {**payload, "messages": [{"role": "user", "content": "Remove my hobbies"}]}
        with patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value='{"message":"Done.","generate_resume":false,"hobbies":""}'):
            response = self.client.post("/api/resume-update", json=removal)
        self.assertEqual(response.json()["changes"], {"hobbies": ""})

    def test_arbitrary_personal_and_resume_updates(self):
        payload = {"messages": [{"role": "user", "content": "Update Favourite book under personal information: Alchemy"}],
                   "resume": {"name": "Ada"}}
        with patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value='{"message":"Updated.","generate_resume":false,"personal_details":"Favourite book: Alchemy"}'):
            response = self.client.post("/api/resume-update", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["changes"], {"personal_details": "Favourite book: Alchemy"})

        payload = {"messages": [{"role": "user", "content": "Make my summary shorter"}],
                   "resume": {"name": "Ada", "summary": "A long existing summary."}}
        with patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value='{"message":"Updated.","generate_resume":false,"summary":"A concise summary."}'):
            response = self.client.post("/api/resume-update", json=payload)
        self.assertEqual(response.json()["changes"], {"summary": "A concise summary."})

    def test_personal_fields_all_templates(self):
        from backend.app import Resume
        from backend.altacv import build_altacv_pdf
        from backend.latexcv import build_latexcv_pdf
        resume = {"name": "Ada", "awards": "Award", "certifications": "Certificate", "passport_number": "AB123456", "passport_valid_until": "2030-10-20", "hobbies": "Chess", "personal_details": "Favourite book: Alchemy"}
        for template in ("classic", "altacv", "latexcv_classic", "latexcv_modern", "latexcv_two_column"):
            with self.subTest(template=template):
                response = self.client.post("/api/export", json={"resume": resume, "format": "docx", "template": template})
                doc = Document(io.BytesIO(response.content))
                paragraphs = doc.paragraphs + [p for table in doc.tables for row in table.rows for cell in row.cells for p in cell.paragraphs]
                text = "\n".join(p.text for p in paragraphs)
                for value in ("AB123456", "2030-10-20", "Chess", "Favourite book: Alchemy"):
                    self.assertIn(value, text)
                self.assertLess(text.index("Awards"), text.index("Personal Information"))
                self.assertLess(text.index("Personal Information"), text.index("Passport number:"))
                self.assertLess(text.index("Personal Information"), text.index("Favourite book: Alchemy"))
                self.assertLess(text.index("Favourite book: Alchemy"), text.index("Certifications"))
                self.assertLess(text.index("Hobbies:"), text.index("Certifications"))
                self.assertTrue(any(run.text == "Passport number: " and run.bold for p in paragraphs for run in p.runs))
        pdf = self.client.post("/api/export", json={"resume": resume, "format": "pdf"})
        text = PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()
        for value in ("AB123456", "2030-10-20", "Chess", "Favourite book: Alchemy"):
            self.assertIn(value, text)
        self.assertLess(text.index("Awards"), text.index("Personal Information"))
        self.assertLess(text.index("Personal Information"), text.index("Passport number:"))
        self.assertLess(text.index("Personal Information"), text.index("Favourite book: Alchemy"))
        self.assertLess(text.index("Favourite book: Alchemy"), text.index("Certifications"))
        self.assertLess(text.index("Hobbies:"), text.index("Certifications"))
        for module, builder in (("backend.altacv", lambda: build_altacv_pdf(Resume(**resume))),
                                ("backend.latexcv", lambda: build_latexcv_pdf(Resume(**resume), "latexcv_two_column")),
                                ("backend.latexcv", lambda: build_latexcv_pdf(Resume(**resume), "latexcv_classic")),
                                ("backend.latexcv", lambda: build_latexcv_pdf(Resume(**resume), "latexcv_modern"))):
            with self.subTest(module=module), patch(f"{module}.compile_tex", return_value=io.BytesIO(b"pdf")) as compiler:
                builder()
                source = compiler.call_args.args[0]
                for value in (r"\textbf{Passport number:}", "AB123456", "2030-10-20", "Chess", "Favourite book: Alchemy"):
                    self.assertIn(value, source)
                self.assertLess(source.index(r"\cvsection{Awards}"), source.index(r"\cvsection{Personal Information}"))
                self.assertLess(source.index(r"\cvsection{Personal Information}"), source.index(r"\textbf{Passport number:}"))
                self.assertLess(source.index(r"\cvsection{Personal Information}"), source.index("Favourite book: Alchemy"))
                self.assertLess(source.index("Favourite book: Alchemy"), source.index(r"\cvsection{Certifications}"))
                self.assertLess(source.index(r"\textbf{Hobbies:}"), source.index(r"\cvsection{Certifications}"))

    def test_personal_information_does_not_repeat_structured_details(self):
        resume = {
            "name": "Ada",
            "passport_number": "Z4255378",
            "passport_valid_until": "01/08/2027",
            "hobbies": "Astrology, Learning Tech",
            "personal_details": (
                "Passport number: Z4255378\n"
                "Validity: 01/08/2027\n"
                "Hobbies\n"
                "Astrology, Learning Tech\n"
                "Favourite book: Alchemy"
            ),
        }
        docx = self.client.post("/api/export", json={"resume": resume, "format": "docx"})
        self.assertEqual(docx.status_code, 200)
        document = Document(io.BytesIO(docx.content))
        docx_text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        self.assertEqual(docx_text.count("Z4255378"), 1)
        self.assertEqual(docx_text.count("01/08/2027"), 1)
        self.assertEqual(docx_text.count("Astrology, Learning Tech"), 1)
        self.assertIn("Favourite book: Alchemy", docx_text)

        pdf = self.client.post("/api/export", json={"resume": resume, "format": "pdf"})
        pdf_text = PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()
        self.assertEqual(pdf_text.count("Z4255378"), 1)
        self.assertEqual(pdf_text.count("01/08/2027"), 1)
        self.assertEqual(pdf_text.count("Astrology, Learning Tech"), 1)
        self.assertIn("Favourite book: Alchemy", pdf_text)

    def test_json_duplicate_is_removed_from_draft_and_update(self):
        personal = {"passport_number": "AB123456", "passport_valid_until": "01/08/2030", "hobbies": "Chess, Reading"}
        duplicated = json.dumps(personal)
        with patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value=json.dumps({**personal, "personal_details": duplicated})):
            response = self.client.post("/api/draft", json={"messages": self.messages})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["personal_details"], "")

        payload = {"messages": [{"role": "user", "content": "Add the details"}], "resume": {**personal, "personal_details": duplicated}}
        with patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value='{"message":"Already included.","generate_resume":false}'):
            response = self.client.post("/api/resume-update", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["resume"]["personal_details"], "")
        self.assertEqual(response.json()["resume"]["passport_number"], personal["passport_number"])

        payload = {"messages": [{"role": "user", "content": "Passport AB123456 valid until 01/08/2030; hobbies Chess, Reading"}],
                   "resume": {"name": "Ada"}}
        result = {"message": "Updated.", "generate_resume": False, **personal, "personal_details": duplicated}
        with patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value=json.dumps(result)):
            response = self.client.post("/api/resume-update", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["changes"], personal)
        self.assertEqual(response.json()["resume"]["personal_details"], "")

        pdf = self.client.post("/api/export", json={"resume": {**personal, "personal_details": duplicated}, "format": "pdf"})
        self.assertEqual(pdf.status_code, 200)
        pdf_text = PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()
        self.assertEqual(pdf_text.count("AB123456"), 1)
        self.assertNotIn('"passport_number"', pdf_text)

    def test_json_cleanup_preserves_distinct_details(self):
        from backend.app import Resume
        data = {"passport_number": "AB123456", "passport_valid_until": "01/08/2030", "hobbies": "Chess, Reading"}
        details = 'Favourite book: Alchemy\n```json\n{\n  "passport_number": "AB123456",\n  "hobbies": "Chess, Reading",\n  "favorite_color": "Blue"\n}\n```\nOther information'
        result = Resume(**data, personal_details=details).personal_details
        self.assertIn("Favourite book: Alchemy", result)
        self.assertIn("favorite_color", result)
        self.assertIn("Other information", result)
        self.assertNotIn("AB123456", result)
        self.assertNotIn("Chess, Reading", result)
        self.assertEqual(json.loads(result.split("```json\n", 1)[1].split("\n```", 1)[0]), {"favorite_color": "Blue"})
        distinct = '{"passport_number":"OTHER","favorite_color":"Blue"}'
        self.assertEqual(Resume(**data, personal_details=distinct).personal_details, distinct)
        self.assertEqual(Resume(personal_details=distinct).personal_details, distinct)

    def test_empty_personal_information_omitted(self):
        response = self.client.post("/api/export", json={"resume": {"name": "Ada", "awards": "Award"}, "format": "pdf"})
        self.assertNotIn("Personal Information", PdfReader(io.BytesIO(response.content)).pages[0].extract_text())

    def test_exports_include_edited_content(self):
        resume = {"name": "Ada Lovelace", "skills": "Python & SQL\nResearch"}
        pdf = self.client.post("/api/export", json={"resume": resume, "format": "pdf"})
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf.headers["content-type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF-"))
        docx = self.client.post("/api/export", json={"resume": resume, "format": "docx"})
        self.assertEqual(docx.status_code, 200)
        text = "\n".join(p.text for p in Document(io.BytesIO(docx.content)).paragraphs)
        self.assertIn("Ada Lovelace", text)
        self.assertIn("Python & SQL", text)
        self.assertIn("Research", text)

    def test_free_text_experience_spacing(self):
        from backend.app import Resume
        from backend.resume_content import experience_lines

        model = Resume(experience=(
            "Technical Lead — Acme\nClient: Example\nJul 2023 – Present | Pune\n"
            "Built systems — reliably\nTechnologies: Python\n"
            "Senior Engineer — Other\nMar 2022 – Jul 2023 | Pune\n"
            "Delivered software\n\n\nIndependent consulting\n"
        ), experience_entries=[{"role": "Analyst", "employer": "Third"}])
        self.assertEqual([line for line, _ in experience_lines(model)], [
            "Technical Lead — Acme", "Client: Example", "Jul 2023 – Present | Pune",
            "Built systems — reliably", "Technologies: Python", "",
            "Senior Engineer — Other", "Mar 2022 – Jul 2023 | Pune",
            "Delivered software", "", "Independent consulting", "", "Analyst — Third",
        ])
        for template in ("classic", "altacv", "latexcv_classic", "latexcv_modern", "latexcv_two_column"):
            with self.subTest(template=template):
                response = self.client.post("/api/export", json={
                    "resume": model.model_dump(), "format": "docx", "template": template,
                })
                self.assertEqual(response.status_code, 200)
                doc = Document(io.BytesIO(response.content))
                paragraphs = doc.paragraphs + [p for table in doc.tables for row in table.rows for cell in row.cells for p in cell.paragraphs]
                text = [p.text for p in paragraphs]
                self.assertEqual(text[text.index("Technologies: Python") + 1:text.index("Senior Engineer — Other")], [""])
                self.assertEqual(text[text.index("Delivered software") + 1:text.index("Independent consulting")], [""])
                self.assertEqual(text[text.index("Independent consulting") + 1:text.index("Analyst — Third")], [""])

    def test_experience_entries_have_one_line_between_companies(self):
        from backend.app import Resume
        from backend.altacv import build_altacv_pdf
        from backend.latexcv import build_latexcv_pdf
        from backend.resume_content import experience_lines

        resume = {"name": "Ada", "experience_entries": [
            {"role": "Engineer", "employer": "Acme", "technologies": "Python"},
            {},
            {"role": "Developer", "employer": "Example", "achievements": "Built tools"},
            {"role": "Analyst", "employer": "Other"},
            {},
        ]}
        model = Resume(**resume)
        lines = experience_lines(model)
        self.assertEqual([line for line, _ in lines], [
            "Engineer — Acme", "Technologies: Python", "",
            "Developer — Example", "Built tools", "", "Analyst — Other",
        ])
        single = Resume(experience_entries=[{}, {"role": "Engineer"}, {}])
        self.assertEqual(experience_lines(single), [("Engineer", "Engineer")])
        for template in ("classic", "altacv", "latexcv_classic", "latexcv_modern", "latexcv_two_column"):
            with self.subTest(template=template):
                response = self.client.post("/api/export", json={"resume": resume, "format": "docx", "template": template})
                self.assertEqual(response.status_code, 200)
                doc = Document(io.BytesIO(response.content))
                paragraphs = doc.paragraphs + [p for table in doc.tables for row in table.rows for cell in row.cells for p in cell.paragraphs]
                text = [p.text for p in paragraphs]
                self.assertEqual(text[text.index("Technologies: Python") + 1:text.index("Developer — Example")], [""])
                self.assertEqual(text[text.index("Built tools") + 1:text.index("Analyst — Other")], [""])
                self.assertNotEqual(text[text.index("Engineer — Acme") + 1], "")
        from reportlab.platypus import Spacer
        with patch("backend.app.Spacer", wraps=Spacer) as spacers:
            response = self.client.post("/api/export", json={"resume": resume, "format": "pdf"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sum(call.args == (1, 14) for call in spacers.call_args_list), 2)

        for module, builder in (
            ("backend.altacv", lambda: build_altacv_pdf(model)),
            ("backend.latexcv", lambda: build_latexcv_pdf(model, "latexcv_classic")),
            ("backend.latexcv", lambda: build_latexcv_pdf(model, "latexcv_modern")),
            ("backend.latexcv", lambda: build_latexcv_pdf(model, "latexcv_two_column")),
        ):
            with self.subTest(module=module), patch(f"{module}.compile_tex", return_value=io.BytesIO(b"pdf")) as compiler:
                builder()
                source = compiler.call_args.args[0]
                self.assertEqual(source.count(r"\vspace{\baselineskip}"), 2)
                self.assertIn("\\textbf{Technologies:} Python\\par\n\\vspace{\\baselineskip}\n\\textbf{Developer — Example}", source)

    def test_structured_sections_and_bold_contacts_across_exports(self):
        resume = {"name": "Ada", "email": "ada@example.com", "contact": "LinkedIn: example.org",
                  "experience_entries": [{"role": "Engineer", "employer": "Acme", "client": "Client A", "dates": "2020", "location": "London", "achievements": "Built tools", "technologies": "Python"}],
                  "education_entries": [{"qualification": "BSc", "institution": "University", "year": "2019"}],
                  "skill_groups": [{"category": "Languages", "skills": "Python"}],
                  "leadership": "Team lead", "awards": "Award", "certifications": "Certificate"}
        for template in ("classic", "altacv", "latexcv_classic", "latexcv_modern", "latexcv_two_column"):
            with self.subTest(template=template):
                response = self.client.post("/api/export", json={"resume": resume, "format": "docx", "template": template})
                self.assertEqual(response.status_code, 200)
                doc = Document(io.BytesIO(response.content))
                text = "\n".join([p.text for p in doc.paragraphs] + [cell.text for table in doc.tables for row in table.rows for cell in row.cells])
                for expected in ("Engineer", "Client A", "BSc", "Languages: Python", "Team lead", "Award", "Certificate"):
                    self.assertIn(expected, text)
                paragraphs = doc.paragraphs + [p for table in doc.tables for row in table.rows for cell in row.cells for p in cell.paragraphs]
                self.assertTrue(any(run.text == "Engineer — Acme" and run.bold for p in paragraphs for run in p.runs))
                self.assertTrue(any(run.text == "Technologies:" and run.bold for p in paragraphs for run in p.runs))
                self.assertTrue(any(run.text == " Python" and not run.bold for p in paragraphs for run in p.runs))
                self.assertTrue(any(run.text == "Email: " and run.bold for p in doc.paragraphs for run in p.runs))
                self.assertTrue(any(run.text == "LinkedIn: " and run.bold for p in doc.paragraphs for run in p.runs))
                self.assertIn("PAGE", doc.sections[0].footer._element.xml)
                self.assertIn("NUMPAGES", doc.sections[0].footer._element.xml)
        pdf = self.client.post("/api/export", json={"resume": resume, "format": "pdf"})
        self.assertEqual(pdf.status_code, 200)
        text = PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()
        for expected in ("Email:", "LinkedIn:", "Engineer", "Client A", "Team lead", "Page 1"):
            self.assertIn(expected, text)
        experience_fonts = []

        def capture_experience_font(text, cm, tm, font_dict, font_size):
            if "Engineer" in text or "Technologies:" in text or text.strip() == "Python":
                experience_fonts.append((text, font_dict.get("/BaseFont"), cm, tm, font_size))

        PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text(visitor_text=capture_experience_font)
        self.assertTrue(any("Engineer" in run[0] and "Bold" in str(run[1]) for run in experience_fonts))
        self.assertTrue(any("Technologies:" in run[0] and "Bold" in str(run[1]) for run in experience_fonts))
        self.assertTrue(any(run[0].strip() == "Python" and "Bold" not in str(run[1]) for run in experience_fonts))
        from backend.app import Resume
        from backend.altacv import build_altacv_pdf
        from backend.latexcv import build_latexcv_pdf
        resume_model = Resume(**resume)
        for module, builder in (
            ("backend.altacv", lambda: build_altacv_pdf(resume_model)),
            ("backend.latexcv", lambda: build_latexcv_pdf(resume_model, "latexcv_two_column")),
            ("backend.latexcv", lambda: build_latexcv_pdf(resume_model, "latexcv_classic")),
        ):
            with self.subTest(module=module), patch(f"{module}.compile_tex", return_value=io.BytesIO(b"pdf")) as compiler:
                builder()
                self.assertIn(r"\textbf{Engineer — Acme}", compiler.call_args.args[0])
                self.assertIn(r"\textbf{Technologies:} Python", compiler.call_args.args[0])

    def test_pdf_import_and_errors(self):
        source = self.client.post("/api/export", json={"resume": {"name": "Ada", "skills": "Python"}, "format": "pdf"})
        response = self.client.post("/api/import-pdf", files={"file": ("resume.pdf", source.content, "application/pdf")})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Python", response.json()["text"])
        invalid = self.client.post("/api/import-pdf", files={"file": ("bad.pdf", b"bad", "application/pdf")})
        self.assertEqual(invalid.status_code, 422)
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        output = io.BytesIO()
        writer.write(output)
        scanned = self.client.post("/api/import-pdf", files={"file": ("blank.pdf", output.getvalue(), "application/pdf")})
        self.assertEqual(scanned.status_code, 422)
        self.assertIn("OCR", scanned.json()["detail"])
        writer.encrypt("password")
        output = io.BytesIO()
        writer.write(output)
        encrypted = self.client.post("/api/import-pdf", files={"file": ("encrypted.pdf", output.getvalue(), "application/pdf")})
        self.assertEqual(encrypted.status_code, 422)
        self.assertIn("Password", encrypted.json()["detail"])
        too_big = self.client.post("/api/import-pdf", files={"file": ("big.pdf", b"%PDF-" + b"x" * (10 * 1024 * 1024), "application/pdf")})
        self.assertEqual(too_big.status_code, 413)

    def test_multipage_classic_footer(self):
        resume = {"name": "Ada", "experience": "\n".join(f"Achievement {i}" for i in range(150))}
        response = self.client.post("/api/export", json={"resume": resume, "format": "pdf"})
        self.assertEqual(response.status_code, 200)
        pages = PdfReader(io.BytesIO(response.content)).pages
        self.assertGreater(len(pages), 1)
        for i, page in enumerate(pages, 1):
            self.assertIn(f"Page {i} of {len(pages)}", page.extract_text())

    def test_contact_deduplication_and_tex_labels(self):
        from backend.app import Resume
        from backend.altacv import build_altacv_pdf
        from backend.latexcv import build_latexcv_pdf
        resume = Resume(name="Ada", email="ada@example.com", contact="Email: ada@example.com\nLinkedIn: example.org",
                        experience_entries=[{"role": "Engineer"}], leadership="Team lead")
        for module, builder in (("backend.altacv", lambda: build_altacv_pdf(resume)),
                                ("backend.latexcv", lambda: build_latexcv_pdf(resume, "latexcv_two_column"))):
            with self.subTest(module=module), patch(f"{module}.compile_tex", return_value=io.BytesIO(b"pdf")) as compiler:
                builder()
                source = compiler.call_args.args[0]
                self.assertEqual(source.count("ada@example.com"), 1)
                self.assertIn(r"\textbf{Email:}", source)
                self.assertIn(r"\textbf{LinkedIn:}", source)
                self.assertIn("Engineer", source)
                self.assertIn("Team lead", source)
                self.assertIn(r"\pageref{LastPage}", source)

    def test_blank_structured_entry_is_not_content(self):
        response = self.client.post("/api/export", json={"resume": {"experience_entries": [{}]}, "format": "pdf"})
        self.assertEqual(response.status_code, 422)

    def test_empty_export_rejected(self):
        response = self.client.post("/api/export", json={"resume": {}, "format": "docx"})
        self.assertEqual(response.status_code, 422)

    def test_altacv_docx_preserves_all_sections(self):
        resume = {"name": "Ada", "summary": "Overview", "experience": "Experience text",
                  "projects": "Project text", "skills": "Python", "education": "University",
                  "additional": "Certification"}
        response = self.client.post("/api/export", json={"resume": resume, "format": "docx", "template": "altacv"})
        self.assertEqual(response.status_code, 200)
        document = Document(io.BytesIO(response.content))
        cells = document.tables[0].rows[0].cells
        self.assertIn("Experience text", cells[0].text)
        self.assertIn("Project text", cells[0].text)
        self.assertIn("Python", cells[1].text)
        self.assertIn("University", cells[1].text)
        self.assertIn("Certification", cells[1].text)

    def test_tex_special_characters_are_escaped(self):
        self.assertEqual(tex_text(r"\input{file} & 50%_#"), r"\textbackslash{}input\{file\} \& 50\%\_\#")

    def test_unknown_template_rejected(self):
        response = self.client.post("/api/export", json={"resume": {"name": "Ada"}, "format": "pdf", "template": "unknown"})
        self.assertEqual(response.status_code, 422)

    def test_recommendation_is_validated_and_uses_user_context(self):
        with patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value='{"template":"latexcv_modern","reason":"Bold heading bars."}') as chat:
            response = self.client.post("/api/recommend-template", json={
                "resume": {"name": "Ada", "headline": "Designer"},
                "messages": self.messages + [{"role": "user", "content": "I prefer a bold style."}],
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["template"], "latexcv_modern")
        self.assertIn("bold style", chat.await_args.args[1][1]["content"])
        self.assertNotIn("What is your name?", chat.await_args.args[1][1]["content"])

    def test_invalid_recommendation_is_reported(self):
        with patch("backend.app.ollama_chat", new_callable=AsyncMock, return_value='{"template":"unknown","reason":"Good"}'):
            response = self.client.post("/api/recommend-template", json={"resume": {"name": "Ada"}, "messages": []})
        self.assertEqual(response.status_code, 502)

    def test_latexcv_docx_and_pdf_dispatch(self):
        for template in ("latexcv_classic", "latexcv_modern", "latexcv_two_column"):
            resume = {"name": "Ada", "experience": "Built tools", "skills": "Python"}
            with self.subTest(template=template):
                docx = self.client.post("/api/export", json={"resume": resume, "format": "docx", "template": template})
                self.assertEqual(docx.status_code, 200)
                doc = Document(io.BytesIO(docx.content))
                text = "\n".join([p.text for p in doc.paragraphs] + [
                    cell.text for table in doc.tables for row in table.rows for cell in row.cells
                ])
                self.assertIn("Built tools", text)
                self.assertIn("Python", text)
                self.assertEqual(len(doc.tables), 1 if template == "latexcv_two_column" else 0)
                with patch("backend.app.build_latexcv_pdf", return_value=io.BytesIO(b"%PDF-test")) as builder:
                    pdf = self.client.post("/api/export", json={"resume": resume, "format": "pdf", "template": template})
                self.assertEqual(pdf.status_code, 200)
                self.assertEqual(builder.call_args.args[1], template)

    def test_two_column_pdf_uses_distinct_columns(self):
        from backend.app import Resume
        from backend.latexcv import build_latexcv_pdf

        with patch("backend.latexcv.compile_tex", return_value=io.BytesIO(b"%PDF-test")) as compiler:
            build_latexcv_pdf(Resume(experience="Experience content", education="Education content"), "latexcv_two_column")
        source = compiler.call_args.args[0]
        self.assertIn(r"\begin{paracol}{2}", source)
        self.assertLess(source.index("Experience content"), source.index(r"\switchcolumn"))
        self.assertGreater(source.index("Education content"), source.index(r"\switchcolumn"))


if __name__ == "__main__":
    unittest.main()
