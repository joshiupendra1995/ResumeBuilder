import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { ArrowDownToLine, ArrowRight, Check, ChevronDown, Copyright, FileText, LoaderCircle, MessageSquareText, Plus, Send, Sparkles } from "lucide-react";
import { applyResumeUpdate } from "./resume-update";
import "./style.css";

const initialMessage = {
  role: "assistant",
  content: "Hi! I’m here to help you create a resume that feels like you. Let’s start with the basics: what’s your name, and what kind of role are you looking for?",
};
const emptyResume = { name: "", headline: "", contact: "", email: "", phone: "", location: "", linkedin: "", github: "", website: "", passport_number: "", passport_valid_until: "", summary: "", experience: "", experience_entries: [], education: "", education_entries: [], skills: "", skill_groups: [], projects: "", leadership: "", awards: "", certifications: "", hobbies: "", personal_details: "", additional: "" };
const sampleResume = { ...emptyResume, name: "Your Name", headline: "Your professional title", email: "you@example.com", summary: "A brief introduction to your experience.", experience: "Your role and accomplishments", education: "Your education", skills: "Your relevant skills", projects: "A project or achievement" };
const contacts = [["email", "Email"], ["phone", "Phone"], ["location", "Location"], ["linkedin", "LinkedIn"], ["github", "GitHub"], ["website", "Website"]];
const personalFields = [["passport_number", "Passport number"], ["passport_valid_until", "Passport valid until"], ["hobbies", "Hobbies"], ["personal_details", "Other personal information"]];
const templates = [
  { id: "classic", name: "Classic", layout: "Simple" },
  { id: "altacv", name: "AltaCV", layout: "Two columns" },
  { id: "latexcv_classic", name: "CV Classic", layout: "Blue headings" },
  { id: "latexcv_modern", name: "CV Modern", layout: "Orange bars" },
  { id: "latexcv_two_column", name: "CV Two-column", layout: "Dark bars" },
];
const fields = [
  ["name", "Full name", "Your name", 1],
  ["headline", "Professional headline", "e.g. Product Designer", 1],
  ...contacts.map(([key, label]) => [key, label, label, 1]),
  ["contact", "Other contact details", "Other contact information", 2],
  ["summary", "Professional summary", "A brief introduction", 4],
  ["experience", "Experience", "Roles, companies, dates, and achievements", 6],
  ["education", "Education", "Schools, degrees, and dates", 4],
  ["skills", "Skills", "Your relevant skills", 3],
  ["projects", "Projects", "Projects and their impact", 4],
  ["leadership", "Leadership", "Leadership roles and impact", 3],
  ["awards", "Awards", "Awards and recognition", 3],
  ...personalFields.map(([key, label]) => [key, label, `${label} (optional)`, key === "hobbies" ? 3 : 1]),
  ["certifications", "Certifications", "Certifications", 3],
  ["additional", "Additional information", "Other relevant details", 3],
];
const sectionFields = fields.filter(([key]) => ["summary", "experience", "education", "skills", "projects", "leadership", "awards", "certifications", "additional"].includes(key)).flatMap((field) => field[0] === "awards" ? [field, ["personal_information", "Personal Information"]] : [field]);
const structuredFields = {
  experience: ["experience_entries", [["role", "Role"], ["employer", "Employer"], ["client", "Client"], ["dates", "Dates"], ["location", "Location"], ["achievements", "Achievements and responsibilities"], ["technologies", "Technologies"]]],
  education: ["education_entries", [["qualification", "Qualification"], ["institution", "Institution"], ["year", "Year"]]],
  skills: ["skill_groups", [["category", "Category"], ["skills", "Skills"]]],
};

function experienceLines(resume) {
  const rawLines = (resume.experience || "").split(/\r?\n/).map((line) => line.trim());
  const lines = [];
  for (const [index, text] of rawLines.entries()) {
    if (!text) {
      if (lines.length && lines.at(-1).text) lines.push({ text: "", boldPrefix: "" });
      continue;
    }
    const isHeading = /^.+\s+[—–-]\s+\S/.test(text)
      && /^(?:client\s*:|(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b|(?:19|20)\d{2}\b|\d{1,2}[/-]\d)/i.test(rawLines.slice(index + 1).find(Boolean) || "");
    if (isHeading && lines.length && lines.at(-1).text) lines.push({ text: "", boldPrefix: "" });
    lines.push({ text, boldPrefix: "" });
  }
  if (lines.length && !lines.at(-1).text) lines.pop();
  let hasEntry = lines.length > 0;
  for (const entry of resume.experience_entries || []) {
    const title = [entry.role, entry.employer].map((value) => (value || "").trim()).filter(Boolean).join(" — ");
    const details = [entry.dates, entry.location].map((value) => (value || "").trim()).filter(Boolean).join(" | ");
    const client = (entry.client || "").trim();
    const achievements = (entry.achievements || "").trim();
    const technologies = entry.technologies?.trim() && `Technologies: ${entry.technologies.trim()}`;
    const entryLines = [
      [title, title],
      [client && `Client: ${client}`, ""],
      [details, ""],
      [achievements, ""],
      [technologies, technologies ? "Technologies:" : ""],
    ].filter(([text]) => text && text.trim());
    if (entryLines.length) {
      if (hasEntry) lines.push({ text: "", boldPrefix: "" });
      for (const [text, boldPrefix] of entryLines) lines.push({ text, boldPrefix });
      hasEntry = true;
    }
  }
  return lines;
}

function sectionText(resume, key) {
  if (key === "personal_information") return personalFields.filter(([field]) => resume[field]?.trim()).map(([field, label]) => field === "personal_details" ? resume[field].trim() : `${label}: ${resume[field].trim()}`).join("\n");
  if (key === "experience") return experienceLines(resume).map(({ text }) => text).join("\n");
  const lines = [resume[key] || ""];
  if (key === "education") for (const e of resume.education_entries || []) lines.push([e.qualification, e.institution, e.year].filter(Boolean).join(" — "));
  if (key === "skills") for (const e of resume.skill_groups || []) lines.push([e.category, e.skills].filter(Boolean).join(": "));
  return lines.filter((line) => line && line.trim()).join("\n");
}

function PreviewSection({ resume, sectionKey, label }) {
  const value = sectionText(resume, sectionKey);
  if (!value) return null;
  return <div className="resume-section"><h3>{label}</h3>{sectionKey === "personal_information"
    ? personalFields.map(([field, title]) => resume[field]?.trim() && <p key={field}>{field === "personal_details" ? resume[field] : <><strong>{title}:</strong> {resume[field]}</>}</p>)
    : sectionKey === "experience"
    ? experienceLines(resume).map(({ text, boldPrefix }, index) => text
      ? <p key={index}>{boldPrefix ? <><strong>{text.slice(0, boldPrefix.length)}</strong>{text.slice(boldPrefix.length)}</> : text}</p>
      : <p className="experience-gap" aria-hidden="true" key={index} />)
    : <p>{value}</p>}</div>;
}

async function request(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.detail === "string" ? data.detail : `Request failed (${response.status}).`);
  }
  return response;
}

function App() {
  const [messages, setMessages] = useState([initialMessage]);
  const [importedSource, setImportedSource] = useState("");
  const [importMessageIndex, setImportMessageIndex] = useState(0);
  const [input, setInput] = useState("");
  const [model, setModel] = useState("qwen2.5:14b");
  const [resume, setResume] = useState(emptyResume);
  const [hasDraft, setHasDraft] = useState(false);
  const [view, setView] = useState("preview");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [exportOpen, setExportOpen] = useState(false);
  const [template, setTemplate] = useState("classic");
  const [recommendation, setRecommendation] = useState("");
  const chatEnd = useRef(null);
  const hasAnswers = !!importedSource || messages.some((message) => message.role === "user");
  const displayedResume = hasDraft ? resume : sampleResume;
  const twoColumns = template === "altacv" || template === "latexcv_two_column";

  function conversationContext(conversation) {
    if (!importedSource) return conversation;
    return [{ role: "user", content: `My existing resume:\n${importedSource}` }, ...conversation.slice(importMessageIndex)];
  }

  useEffect(() => {
    fetch("/api/config").then((response) => {
      if (!response.ok) throw new Error("Could not load configuration");
      return response.json();
    }).then((data) => setModel(data.default_model)).catch(() => {
      setError("Could not connect to the backend. Start the Python server and refresh.");
    });
  }, []);
  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [messages, busy]);

  async function sendMessage(event) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    const next = [...messages, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setError("");
    setRecommendation("");
    setBusy("interview");
    try {
      const directRequest = /^(?:please\s+)?generate my resume(?:\s+(?:now|please))?[.!?]*$/i.test(text);
      const data = directRequest
        ? { generate_resume: true }
        : hasDraft
          ? await (await request("/api/resume-update", { messages: conversationContext(next), resume, model })).json()
          : await (await request("/api/interview", { messages: conversationContext(next), model, has_draft: hasDraft })).json();
      if (hasDraft && !data.generate_resume) {
        setBusy("update");
        const changes = data.changes;
        setResume(applyResumeUpdate(resume, data));
        if (!Object.keys(changes).length) {
          setMessages([...next, { role: "assistant", content: data.message }]);
          return;
        }
        setView("preview");
        setMessages([...next, { role: "assistant", content: "Your resume has been updated. Please review the changes in the preview." }]);
        return;
      }
      if (!data.generate_resume) {
        setMessages([...next, { role: "assistant", content: data.message }]);
        return;
      }
      if (hasDraft && !window.confirm("Generate a new resume? This will replace your current edits.")) {
        setMessages([...next, { role: "assistant", content: "Your existing resume is unchanged. Let me know if you want to continue the interview." }]);
        return;
      }
      const generating = [...next, { role: "assistant", content: "I’ll generate your resume from the details you’ve shared." }];
      setMessages(generating);
      setBusy("draft");
      try {
        await generateDraft(conversationContext(next));
        setMessages([...generating, { role: "assistant", content: "Your resume is ready to review and edit in the preview." }]);
      } catch (err) {
        setMessages([...generating, { role: "assistant", content: "I couldn’t generate your resume. Please say ‘generate my resume’ to try again." }]);
        throw err;
      }
    } catch (err) {
      setError(err.message);
    } finally { setBusy(""); }
  }

  async function generateDraft(conversation) {
    const response = await request("/api/draft", { messages: conversation, model });
    setResume({ ...emptyResume, ...await response.json() });
    setHasDraft(true);
    setRecommendation("");
    setView("preview");
  }

  async function importPdf(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || busy) return;
    if (hasDraft && !window.confirm("Importing will replace your current resume after successful processing. Continue?")) return;
    setError("");
    setBusy("import");
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/import-pdf", { method: "POST", body: form });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(typeof data.detail === "string" ? data.detail : "Could not import PDF.");
      }
      const { text } = await response.json();
      await generateDraft([{ role: "user", content: `My existing resume:\n${text}` }]);
      setImportedSource(text);
      setImportMessageIndex(messages.length);
      setMessages([...messages, { role: "assistant", content: "Your imported resume is ready. No chat details are required; review and edit it, or add more information here if you wish." }]);
    } catch (err) { setError(err.message); }
    finally { setBusy(""); }
  }

  async function regenerateDraft() {
    if (!hasAnswers || busy) return;
    if (!window.confirm("Generate a new resume? This will replace your current edits.")) return;
    setError("");
    setBusy("draft");
    try { await generateDraft(conversationContext(messages)); }
    catch (err) { setError(err.message); }
    finally { setBusy(""); }
  }

  async function recommendTemplate() {
    if (!hasDraft || busy) return;
    setError("");
    setBusy("recommend");
    try {
      const response = await request("/api/recommend-template", { resume, messages: importedSource ? messages.slice(importMessageIndex) : messages, model });
      const data = await response.json();
      setTemplate(data.template);
      setRecommendation(data.reason);
    } catch (err) { setError(err.message); }
    finally { setBusy(""); }
  }

  async function download(format) {
    setExportOpen(false);
    setError("");
    setBusy(format);
    try {
      const response = await request("/api/export", { resume, format, template });
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `resume-${template}.${format}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) { setError(err.message); }
    finally { setBusy(""); }
  }

  function reset() {
    setMessages([initialMessage]);
    setImportedSource("");
    setImportMessageIndex(0);
    setResume(emptyResume);
    setHasDraft(false);
    setInput("");
    setError("");
    setView("preview");
    setTemplate("classic");
    setRecommendation("");
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><img className="brand-icon" src="/resume-genie-icon.svg" alt="" /><div>Resume<span> Genie</span></div></div>
        <div className="top-actions"><button className="new-button" onClick={reset} disabled={!!busy}><Plus size={16} /> New chat</button></div>
      </header>
      <main>
        <section className="intro" aria-labelledby="hero-title">
          <div className="hero-copy">
            <h1 id="hero-title">Build a resume that opens <span>new opportunities.</span></h1>
            <p>Turn your experience into a resume you’re proud to share. Just tell us about yourself, and let Genie help with the rest.</p>
          </div>
          <div className="hero-art" aria-hidden="true">
            <div className="hero-orbit orbit-one" /><div className="hero-orbit orbit-two" />
            <div className="hero-document">
              <div className="hero-doc-top"><div className="hero-doc-avatar" /><div><i /><i /></div></div>
              <div className="hero-doc-section"><b /><i /><i /><i /></div>
              <div className="hero-doc-section"><b /><i /><i /></div>
              <div className="hero-doc-section"><b /><i /><i /></div>
            </div>
            <div className="hero-sparkle"><Sparkles size={19} /></div>
            <div className="hero-check"><Check size={17} /></div>
          </div>
        </section>
        <div className="workspace-heading"><div><div className="workspace-kicker">YOUR WORKSPACE</div><h2>Let’s build your resume</h2><p>Share your experience, then make it yours.</p></div><div className="steps"><div className="step active"><span>1</span> Your story</div><div className="step-line" /><div className={`step ${hasDraft ? "active" : ""}`}><span>{hasDraft ? <Check size={14} /> : "2"}</span> Review & export</div></div></div>
        {error && <div className="error" role="alert">{error}<button onClick={() => setError("")} aria-label="Dismiss error">×</button></div>}
        <div className="workspace">
          <section className="panel chat-panel">
            <div className="panel-header"><div className="panel-title"><div className="panel-icon"><MessageSquareText size={18} /></div><div><h2>Your conversation</h2><p>Let’s get to know your experience</p></div></div></div>
            <div className="chat-body">
              <div className="chat-label">YOUR RESUME JOURNEY STARTS HERE</div>
              {messages.map((message, index) => <div className={`message-row ${message.role}`} key={index}>
                {message.role === "assistant" && <div className="avatar"><Sparkles size={16} /></div>}
                <div className="message-content"><div className="message-meta">{message.role === "assistant" ? "RESUME ASSISTANT" : "YOU"}</div><div className="bubble">{message.content}</div></div>
              </div>)}
              {busy === "interview" && <div className="thinking"><LoaderCircle size={15} className="spin" /> Thinking about your answer...</div>}
              {busy === "draft" && <div className="thinking" role="status"><LoaderCircle size={15} className="spin" /> Generating your resume...</div>}
              <div ref={chatEnd} />
            </div>
            <div className="chat-bottom">
              <form className="composer" onSubmit={sendMessage}><textarea aria-label="Your message" placeholder="Ask anything or share what you'd like on your resume..." value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form.requestSubmit(); } }} /><button aria-label="Send message" disabled={!input.trim() || !!busy}><Send size={17} /></button></form>
              <div className="composer-note"><span>{hasDraft ? "Ask to update any resume details, or edit directly." : "When ready, say “generate my resume”."}</span><label>Model <input aria-label="Ollama model" value={model} onChange={(event) => setModel(event.target.value)} disabled={!!busy} /></label></div>
            </div>
          </section>
          <section className="panel resume-panel">
            <div className="panel-header"><div className="panel-title"><div className="panel-icon peach"><FileText size={18} /></div><div><h2>Your resume</h2><p>Your story, taking shape</p></div></div><div className="tabs"><button className={view === "preview" ? "selected" : ""} onClick={() => setView("preview")}>Preview</button><button className={view === "edit" ? "selected" : ""} onClick={() => setView("edit")}>Edit</button></div></div>
            <div className="import-bar"><label className="import-button">Import existing PDF<input type="file" accept=".pdf,application/pdf" disabled={!!busy} onChange={importPdf} /></label><span>{busy === "import" ? "Importing and generating..." : "No chat required. Text-based PDFs only; review AI-extracted details."}</span></div>
            <div className="template-picker"><div className="template-picker-heading"><strong>Choose a template</strong><button className="recommend-button" onClick={recommendTemplate} disabled={!hasDraft || !!busy}>{busy === "recommend" ? "Choosing..." : "Suggest for me"}</button></div><div className="template-options" role="group" aria-label="Choose a template">{templates.map((item) => <button key={item.id} type="button" className={`template-option ${template === item.id ? "chosen" : ""}`} aria-pressed={template === item.id} disabled={!!busy} onClick={() => { setTemplate(item.id); setRecommendation(""); }}><strong>{item.name}</strong><small>{item.layout}</small></button>)}</div><span>{recommendation ? `AI suggestion: ${recommendation}` : "Choose any design. Preview and DOCX are approximate; PDF uses the selected layout."}</span></div>
            <div className="resume-body">
              {busy === "draft" && <div className="review-notice" role="status"><LoaderCircle size={14} className="spin" /> Generating your resume from the conversation...</div>}
              {hasDraft && <div className="review-notice">AI can make mistakes. Check every detail before exporting. Passport information is optional and sensitive.</div>}
              {!hasDraft && <div className="sample-notice">Sample preview — ask the assistant to generate your resume when you’re ready.</div>}
              {hasDraft && view === "edit" ? <div className="edit-form"><p>Make it yours. Your changes will appear in the exported file.</p><fieldset disabled={!!busy}>{fields.map(([key, label, placeholder, rows]) => <React.Fragment key={key}>{key === "passport_number" && <h3>Personal Information</h3>}<label>{label}{structuredFields[key] && " (additional free text)"}<textarea rows={rows} value={resume[key] || ""} placeholder={placeholder} onChange={(event) => { setResume({ ...resume, [key]: event.target.value }); setRecommendation(""); }} /></label>{structuredFields[key] && (() => {
                const [arrayKey, entryFields] = structuredFields[key];
                const entries = resume[arrayKey] || [];
                return <div className="structured-editor"><strong>{label} entries</strong>{entries.map((entry, index) => <div className="structured-entry" key={index}>{entryFields.map(([field, title]) => <label key={field}>{title}<textarea rows={field === "achievements" ? 3 : 1} value={entry[field] || ""} onChange={(event) => { const updated = entries.map((item, i) => i === index ? { ...item, [field]: event.target.value } : item); setResume({ ...resume, [arrayKey]: updated }); setRecommendation(""); }} /></label>)}<button type="button" onClick={() => { setResume({ ...resume, [arrayKey]: entries.filter((_, i) => i !== index) }); setRecommendation(""); }}>Remove entry</button></div>)}<button type="button" disabled={entries.length >= 30} onClick={() => { setResume({ ...resume, [arrayKey]: [...entries, Object.fromEntries(entryFields.map(([field]) => [field, ""]))] }); setRecommendation(""); }}>Add {label.toLowerCase()} entry</button></div>;
              })()}</React.Fragment>)}</fieldset></div>
                : <div className={`resume-paper ${template === "altacv" ? "altacv-preview" : template === "latexcv_classic" ? "latexcv-classic-preview" : template === "latexcv_modern" ? "latexcv-modern-preview" : template === "latexcv_two_column" ? "latexcv-two-preview" : ""}`}><div className="paper-heading"><h2>{displayedResume.name || "Your name"}</h2>{displayedResume.headline && <div>{displayedResume.headline}</div>}{contacts.map(([key, label]) => displayedResume[key]?.trim() && <p key={key}><strong>{label}:</strong> {displayedResume[key]}</p>)}{displayedResume.contact?.split("\n").map((line, i) => { const match = line.trim().match(/^(Email|Phone|Location|LinkedIn|GitHub|Website):\s*(.*)$/i); if (match && displayedResume[match[1].toLowerCase()]?.trim().toLowerCase() === match[2].trim().toLowerCase()) return null; return line.trim() && <p key={i}>{match ? <><strong>{match[1]}:</strong> {match[2]}</> : line}</p>; })}</div>{twoColumns ? <div className="preview-columns">{[["summary", "experience", "projects"], ["skills", "education", "leadership", "awards", "personal_information", "certifications", "additional"]].map((group, index) => <div key={index}>{group.map((key) => <PreviewSection key={key} resume={displayedResume} sectionKey={key} label={sectionFields.find(([field]) => field === key)[1]} />)}</div>)}</div> : sectionFields.map(([key, label]) => <PreviewSection key={key} resume={displayedResume} sectionKey={key} label={label} />)}</div>}
            </div>
            <div className="resume-bottom"><div className="bottom-copy"><Sparkles size={15} /><span>{busy === "draft" ? "Generating your resume..." : hasDraft ? "AI can make mistakes. Check every detail." : "Tell the assistant when you’re ready to generate."}</span></div><div className="bottom-actions">{hasDraft && <button className="draft-button" onClick={regenerateDraft} disabled={!!busy}>{busy === "draft" ? <LoaderCircle size={16} className="spin" /> : <Sparkles size={16} />}Regenerate <ArrowRight size={15} /></button>}<div className="export-wrap"><button className="export-button" disabled={!hasDraft || !!busy} onClick={() => setExportOpen(!exportOpen)}><ArrowDownToLine size={16} /> Export <ChevronDown size={14} /></button>{exportOpen && <div className="export-menu"><button onClick={() => download("pdf")}>Download PDF</button><button onClick={() => download("docx")}>Download DOCX</button></div>}</div></div></div>
          </section>
        </div>
        <footer className="site-footer"><Copyright size={15} aria-hidden="true" /><span>© {new Date().getFullYear()} Upendra Joshi. All rights reserved.</span></footer>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
