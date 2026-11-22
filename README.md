# Resume Genie

Resume Genie helps you create or improve a resume without starting from a blank page. Chat about your experience or import an existing CV, then review, edit, and export the result. It uses Ollama so you can run the AI model locally.

## Features

- **Create through chat:** share your background and ask the assistant to generate a resume.
- **Import a CV:** upload an existing text-based PDF to create an editable draft without answering interview questions.
- **Update and edit:** ask for changes in chat or use the editor for contact details, experience, education, skills, projects, and other sections. Experience, education, and skills support repeatable structured entries as well as free text.
- **Preview and choose a design:** select Classic, AltaCV, CV Classic, CV Modern, or CV Two-column, or ask the assistant to suggest a template.
- **Export:** download your resume as PDF or DOCX. Both include a name and page-number footer.
- **Regenerate or start fresh:** regenerate from the conversation or imported CV, or use **New chat** to clear the current draft and conversation.

## Tech stack

- **Frontend:** React, Vite, and Lucide icons
- **Backend:** Python, FastAPI, and Pydantic
- **AI:** Ollama
- **Documents:** pypdf for PDF import; ReportLab, python-docx, and Tectonic/LaTeX for exports

## Getting started

### Requirements

- Python 3.10+ and Node.js 20.19+ or 22.12+
- [Ollama](https://ollama.com/) running with a model installed
- A Unicode TrueType font for Classic PDF export. macOS Arial Unicode and Linux DejaVu Sans are detected automatically; otherwise set `RESUME_PDF_FONT` to a `.ttf` file. Windows setup is shown below.
- [Tectonic](https://tectonic-typesetting.github.io/) on `PATH` for AltaCV and LaTeX CV PDF exports. Its first run may download TeX packages.

### Install and run on macOS or Linux

Start Ollama, then run these commands from the project directory:

```sh
ollama pull qwen2.5:14b
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
npm install
./start.sh
```

Open http://127.0.0.1:5173. Keep the terminal open; press Ctrl+C to stop the app. Ports 5173 and 8000 must be available.

### Install and run on Windows

Start Ollama, then open PowerShell in the project directory:

```powershell
ollama pull qwen2.5:14b
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
npm.cmd install
```

In the same PowerShell window, set a font for Classic PDF export and start the backend:

```powershell
$env:RESUME_PDF_FONT = "$env:WINDIR\Fonts\arial.ttf"
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Open a second PowerShell window in the project directory and start the frontend:

```powershell
npm.cmd run dev -- --port 5173 --strictPort
```

Open http://127.0.0.1:5173. Keep both windows open and press Ctrl+C in each to stop the servers. Ports 5173 and 8000 must be available. The `start.sh` script is for macOS/Linux; Windows uses the two commands above.

### Configure Ollama

The default model is `qwen2.5:14b`. To choose another installed model for the current session, enter its name in the **Model** field beside the chat. To change the default or connect to a different Ollama server, set environment variables before starting:

On macOS/Linux:

```sh
OLLAMA_MODEL=llama3:latest OLLAMA_URL=http://127.0.0.1:11434 ./start.sh
```

On Windows, set these in the PowerShell window **before starting the backend**:

```powershell
$env:OLLAMA_MODEL = "llama3:latest"
$env:OLLAMA_URL = "http://127.0.0.1:11434"
```

Pull the chosen model first, for example `ollama pull llama3:latest`. Model quality and speed depend on your hardware and the model.

## How to use

### Create a resume through chat

1. Tell the assistant about your experience, education, skills, and the role you want.
2. Say **“generate my resume”** when ready, or confirm the assistant's offer to generate it.
3. Review the draft, then request changes in chat or use **Edit**.

### Upload an existing CV

1. Select **Import existing PDF** and choose your CV.
2. Review the generated draft in **Preview** or **Edit**; chat is optional.
3. Add details through chat or edit the fields directly.

Import accepts text-based PDFs up to 10 MB and 20 pages. Scanned, image-only, and password-protected PDFs are not supported. Importing or regenerating replaces an existing draft only after confirmation and successful generation.

### Finish and export

Choose a template, optionally use **Suggest for me**, and select **Export** to download a PDF or DOCX. The preview and DOCX approximate the selected design; inspect the exported document before sharing. Experience entries have a blank line between companies; in free text, add a blank line where automatic separation does not apply.

## Privacy and limitations

The conversation and draft are kept in the current browser tab and are lost on refresh or **New chat**. The app has no authentication and is intended for local use. Resume data is sent to the configured Ollama server, so a remote `OLLAMA_URL` sends it off your device. Review AI-generated content for accuracy and include sensitive personal details only when needed.

## Template credits

AltaCV uses [AltaCV](https://github.com/liantze/AltaCV/tree/91373530c55843533a4de12a29d28896f9b14c0d) by LianTze Lim ([LPPL 1.3 or later](backend/vendor/altacv/LICENSE.md)). The LaTeX CV templates use adapted preambles from [latexcv](https://github.com/jankapunkt/latexcv/tree/c4284b2ac9d20ba751e272fc805bb00accc6f1a8) by Jan Küster ([MIT license](backend/vendor/latexcv/LICENSE)).
