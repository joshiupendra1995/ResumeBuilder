# Resume Genie

A local-first resume builder. Answer an Ollama-powered interview, generate an editable draft, and download it as PDF or DOCX. Review the draft carefully: language models can make mistakes even when instructed not to invent details.

## Requirements

- Python 3.10+ and Node.js 20.19+ or 22.12+
- [Ollama](https://ollama.com/) running locally
- A TrueType font for PDF export. macOS Arial Unicode and Linux DejaVu Sans are detected automatically; otherwise set `RESUME_PDF_FONT` to a Unicode `.ttf` file.
- For AltaCV and LaTeX CV PDF exports, [Tectonic](https://tectonic-typesetting.github.io/) on `PATH` (on macOS, `brew install tectonic`). Tectonic downloads and caches TeX packages from its configured bundle on first use; this requires an internet connection and can take several minutes.

## Run locally

First-time setup, from this directory:

```sh
ollama pull qwen2.5:14b  # skip if already installed
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
npm install
```

Start Ollama, then launch both servers from one terminal:

```sh
./start.sh
```

Open http://127.0.0.1:5173. Keep the terminal and Ollama running; press Ctrl+C in the terminal to stop both app servers. The script checks dependencies and Ollama but does not install or start them. It requires ports 8000 and 5173 to be free.

Answer the assistant's questions, then tell it **“generate my resume”** when you are ready, or confirm when it offers to generate it. Your resume will appear in the preview. Use **Edit** to correct it and **Export** to download PDF or DOCX. Include the actual details in your answers rather than just saying "yes": drafting uses only your messages to avoid mistaking the assistant's suggestions for facts. Regenerating a resume replaces edits only after confirmation; if generation fails, ask the assistant to try again.

Use **Import existing PDF** to extract text locally and generate an editable draft using the selected Ollama model. No chat answers are required, and earlier chat messages are not used in the imported draft. You can edit and export it immediately, or optionally add information in the chat afterward. Regeneration uses the imported PDF and subsequent chat messages, not earlier messages; it replaces manual edits after confirmation. Import supports text-based PDFs up to 10 MB and 20 pages; password-protected and scanned/image-only files are not supported (OCR is not included). Importing replaces an existing draft only after confirmation and successful generation. Always verify extracted details. The editor supports separate contact fields, repeatable experience and education entries, categorized skills, leadership, awards, and certifications. Free-text fields remain available for other details; avoid repeating the same information in both forms. Exported documents include a name and page-number footer; DOCX page counts update when opened in a word processor.

Experience entries are separated by a blank line. In free-text experience, blank lines are preserved and common “role — employer” headings followed by a client or date are separated automatically. For other formats, add a blank line between companies in the editor.

Passport number, passport validity, hobbies and other personal details are optional and appear under **Personal Information**, below Awards. Passport numbers are sensitive: include them only when needed and be careful where you share exported resumes. You can ask the assistant to update any resume detail in your own words, including additional information such as a favorite book, or make changes in **Edit**. Review all updates in the preview before exporting. When importing a PDF, check and remove any passport details you do not wish to export. The configured Ollama server receives the information you provide; a remote `OLLAMA_URL` sends it off your device.

Choose a template using the design buttons above the preview. Before a draft is created, the preview displays sample text. The available options include Classic, AltaCV, and LaTeX CV Classic, Modern, and Two-column. After creating a draft, choose **Suggest for me** to ask the selected Ollama model to recommend a template based on your answers and draft; you can always select another. Mention any style preferences in your answers. The preview and DOCX are approximations, not identical LaTeX renders; inspect the downloaded document for final formatting. The LaTeX templates require Tectonic for PDF generation.

The AltaCV class is by LianTze Lim, sourced from [AltaCV](https://github.com/liantze/AltaCV/tree/91373530c55843533a4de12a29d28896f9b14c0d) and distributed under the [LaTeX Project Public License 1.3 or later](backend/vendor/altacv/LICENSE.md). LaTeX CV Classic, Modern and Two-column use adapted preambles from [Jan Küster's latexcv collection](https://github.com/jankapunkt/latexcv/tree/c4284b2ac9d20ba751e272fc805bb00accc6f1a8), under the [MIT license](backend/vendor/latexcv/LICENSE); their sample contents are not used in generated resumes. These are selected adaptations, not the entire collection.

Your conversation and draft are kept only in the open browser tab and are lost on refresh or when you start over. Requests and exports go through the local Python server to local Ollama; no account or external AI service is required. For LaTeX-based templates, the resume is temporarily written to a local temporary directory and removed after compilation; Tectonic may access the internet to fetch TeX packages. Avoid exposing the development servers to the network: they are intended for a single local user and have no authentication.

## Model choice

Of the models already installed, **`qwen2.5:14b` is the recommended starting point**: it is an instruction-following model with documented structured JSON support, useful for the interview and resume extraction. It is larger and may respond more slowly than `llama3:latest`; select the latter in the model field if speed or memory is more important, and compare the results on your own experience. `nomic-embed-text` is an embedding model, not a conversational model, so it is not suitable for this task. There is no universally best model; quality and performance depend on your hardware and inputs.

Set `OLLAMA_MODEL` before starting the backend to change the default, or edit the model name in the UI. Set `OLLAMA_URL` to change the Ollama server URL (default `http://127.0.0.1:11434`); using a remote URL sends your resume data to that server.

Sources: [Qwen2.5 on Ollama](https://ollama.com/library/qwen2.5), [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [nomic-embed-text on Ollama](https://ollama.com/library/nomic-embed-text).

## Verify

```sh
python -m unittest discover -s backend/tests
npm run build
```
# ResumeBuilder
