import { useEffect, useState } from "react";
import { Bundle } from "./types";
import { Poster } from "./Poster";

type Job = { job_id: string; paper_id: string; title: string; status: string; spent_usd: string };

export function App() {
  const [bundle, setBundle] = useState<Bundle | null>(window.__PAPERCRAFT_POSTER__ || null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (bundle) return;
    const job = new URLSearchParams(location.search).get("job");
    if (job) {
      fetch(`/api/jobs/${job}/bundle`).then((r) => r.json()).then(setBundle).catch(() => setMessage("Could not load this job."));
    } else {
      fetch("/api/jobs").then((r) => r.json()).then(setJobs).catch(() => undefined);
    }
  }, [bundle]);

  if (bundle) return <Poster bundle={bundle} />;

  async function upload(file: File) {
    setBusy(true);
    setMessage("Checking the PDF and creating DocumentIR…");
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await fetch("/api/jobs", { method: "POST", body });
      const job = await response.json();
      if (!response.ok) throw new Error(job.detail || "Upload failed");
      setMessage(`${job.title || file.name} passed PDF checks. DocumentIR is ready; semantic analysis still requires an explicit model-stage run.`);
      const refreshed = await fetch("/api/jobs").then((r) => r.json());
      setJobs(refreshed);
      setBusy(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed");
      setBusy(false);
    }
  }

  return (
    <main className="studio-shell">
      <section className="studio-hero">
        <p className="eyebrow">PAPERCRAFT · GROUNDED POSTER STUDIO</p>
        <h1>Turn a paper into an evidence-first visual explanation.</h1>
        <p>Upload an English text PDF. PaperCraft keeps every claim, number, formula, and visual connected to its source.</p>
        <label className={`upload-card ${busy ? "busy" : ""}`}>
          <input type="file" accept="application/pdf" disabled={busy} onChange={(event) => event.target.files?.[0] && upload(event.target.files[0])} />
          <span>{busy ? "Working…" : "Choose a PDF"}</span>
          <small>Scanned, textless, encrypted, and non-English PDFs are rejected clearly.</small>
        </label>
        {message && <p className="studio-message">{message}</p>}
      </section>
      <section className="jobs-panel">
        <div className="section-heading"><span>Recent work</span><span>{jobs.length} jobs</span></div>
        {jobs.length === 0 ? <p className="empty-state">No jobs yet. The reviewed AMP development paper is available through the demo command.</p> : jobs.map((job) => (
          <a className="job-row" href={`?job=${job.job_id}`} key={job.job_id}>
            <span><strong>{job.title}</strong><small>{job.paper_id}</small></span>
            <span className={`status status-${job.status}`}>{job.status.replaceAll("_", " ")}</span>
            <span>${job.spent_usd}</span>
          </a>
        ))}
      </section>
    </main>
  );
}
