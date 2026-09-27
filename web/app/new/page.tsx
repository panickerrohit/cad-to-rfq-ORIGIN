"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, JobSummary } from "@/lib/api";
import { StatusPill } from "@/components/StatusPill";

export default function NewRfq() {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<JobSummary[] | null>(null);

  useEffect(() => {
    api.listJobs().then(setRecent).catch((e) => setError(e.message));
  }, []);

  async function upload(file: File | undefined) {
    if (!file) return;
    setError(null);
    if (!/\.(step|stp)$/i.test(file.name)) {
      setError("Upload a STEP file (.step or .stp). DWG support comes after the MVP.");
      return;
    }
    setBusy(`Uploading ${file.name}…`);
    try {
      const job = await api.upload(file);
      router.push(`/jobs/${job.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  async function demo() {
    setError(null);
    setBusy("Loading the demo bracket…");
    try {
      const job = await api.demo();
      router.push(`/jobs/${job.id}?demo=1`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  return (
    <main className="page">
      <div className="wrap" style={{ maxWidth: 860 }}>
        <div className="page-head">
          <div>
            <h1>New RFQ</h1>
            <p className="muted" style={{ margin: "6px 0 0" }}>Start with the 3D model of one part.</p>
          </div>
        </div>

        {error && <div className="alert error" style={{ marginBottom: 16 }}>{error}</div>}

        <div
          className={`drop ${over ? "over" : ""}`}
          onClick={() => !busy && input.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); if (!busy) upload(e.dataTransfer.files[0]); }}
        >
          <input ref={input} type="file" accept=".step,.stp" onChange={(e) => upload(e.target.files?.[0])} />
          {busy ? (
            <div className="working" style={{ padding: 0 }}><div className="spinner" /><b>{busy}</b></div>
          ) : (
            <>
              <div className="icon">⬆</div>
              <h3 style={{ marginBottom: 4 }}>Drop a STEP file here, or click to choose</h3>
              <p className="muted small" style={{ margin: 0 }}>.step or .stp · one solid part · up to 50 MB</p>
            </>
          )}
        </div>

        <div className="row" style={{ justifyContent: "center", margin: "18px 0 40px" }}>
          <span className="muted small">No file to hand?</span>
          <button className="btn" onClick={demo} disabled={!!busy}>Use the demo bracket</button>
        </div>

        <div className="card">
          <div className="card-head"><h3>Recent RFQs</h3></div>
          {recent === null ? (
            <p className="muted card-pad" style={{ margin: 0 }}>Loading…</p>
          ) : recent.length === 0 ? (
            <p className="muted card-pad" style={{ margin: 0 }}>Nothing yet. Your RFQs will show up here.</p>
          ) : (
            <table className="jobs-table">
              <thead><tr><th>Part</th><th>File</th><th>Status</th><th>Created</th></tr></thead>
              <tbody>
                {recent.map((j) => (
                  <tr key={j.id}>
                    <td><Link href={`/jobs/${j.id}`}><b>{j.part_number || "Untitled"}</b></Link></td>
                    <td className="mono small">{j.filename}</td>
                    <td><StatusPill status={j.status} /></td>
                    <td className="muted small">{j.created_at ? new Date(j.created_at).toLocaleString() : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </main>
  );
}
