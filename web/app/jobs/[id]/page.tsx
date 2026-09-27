"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, Job } from "@/lib/api";
import { CadPanel } from "@/components/CadPanel";
import { EngFormView } from "@/components/EngFormView";
import { FlagList, ReviewView } from "@/components/ReviewView";
import { StatusPill } from "@/components/StatusPill";

export default function JobPage() {
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [supplierCopy, setSupplierCopy] = useState(true);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const next = await api.get(id);
        if (active) { setJob(next); setError(null); }
      } catch (e) {
        if (active) setError((e as Error).message);
      }
      if (active) timer = setTimeout(refresh, 1500);
    }
    refresh();
    return () => { active = false; clearTimeout(timer); };
  }, [id]);

  async function run(action: () => Promise<Job>) {
    setBusy(true); setError(null);
    try { setJob(await action()); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  const review = job && (job.status === "review" || job.status === "done");
  return (
    <main className="page"><div className="wrap stack">
      <Link href="/new">← All RFQs</Link>
      {error && <div className="alert error" role="alert">{error}</div>}
      {!job ? <p>Loading RFQ…</p> : <>
        <div className="page-head row">
          <h1>{job.form?.part_number || job.cad_filename}</h1>
          <StatusPill status={job.status} />
        </div>
        {job.draft_mode === "mock" && <div className="alert">Demo mode: this draft uses rule-based sample text.</div>}
        {job.error && <div className="alert error" role="alert">{job.error}</div>}
        {job.working && <div className="working"><div className="spinner" />Processing your RFQ…</div>}
        <CadPanel job={job} />
        {(job.status === "awaiting_form" || (editing && review)) &&
          <EngFormView job={job} onSaved={(next) => { setJob(next); setEditing(false); }}
            onCancel={editing ? () => setEditing(false) : undefined} />}
        {review && !editing && <>
          <div className="card card-pad"><FlagList flags={job.flags} /></div>
          <div className="row">
            <button className="btn" onClick={() => setEditing(true)}>Edit part details</button>
            <button className="btn" disabled={busy || !job.unapproved.length}
              onClick={() => run(() => api.approveAll(id))}>Approve all AI fields</button>
            <span className="muted small">{job.unapproved.length} fields need approval</span>
          </div>
          <ReviewView job={job} onJob={setJob} onEditForm={() => setEditing(true)} />
          <div className="card card-pad row">
            <label><input type="checkbox" checked={supplierCopy}
              onChange={(e) => setSupplierCopy(e.target.checked)} /> Supplier copy (hide internal provenance)</label>
            <button className="btn primary" disabled={busy || !!job.unapproved.length}
              onClick={() => run(() => api.render(id, supplierCopy))}>Export PDF</button>
            {job.pdf_url && <a className="btn" href={api.url(job.pdf_url)} target="_blank" rel="noreferrer">Download PDF</a>}
          </div>
        </>}
      </>}
    </div></main>
  );
}
