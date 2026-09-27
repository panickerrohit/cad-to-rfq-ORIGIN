"use client";

import { useState } from "react";
import { api, display, Field, Flag, Job, label } from "@/lib/api";

const AI_ORDER = ["scope_of_work", "process_notes", "inspection_requirements", "packaging", "quote_form_questions"];
const ENG_ORDER = ["part_name", "part_number", "revision", "material", "general_tolerance", "critical_dims", "finish",
  "qty_breaks", "quote_due", "target_delivery", "certs", "packaging", "buyer", "notes"];
const CAD_ORDER = ["bbox_mm", "volume_mm3", "surface_area_mm2", "solid_count", "source_filename"];
const SEV_RANK = { error: 0, warn: 1, info: 2 } as const;

type Kind = "text" | "list" | "qty" | "form" | "readonly";

function kindOf(key: string, f: Field): Kind {
  if (f.source === "CAD") return "readonly";
  if (key === "qty_breaks") return "qty";
  const v = f.value;
  if (Array.isArray(v)) return v.length && typeof v[0] === "object" ? "form" : "list";
  if (v && typeof v === "object") return "form";
  return "text";
}

function toText(kind: Kind, v: unknown) {
  if (v == null) return "";
  if (kind === "qty") return (v as number[]).join(", ");
  if (kind === "list") return (v as unknown[]).map(String).join("\n");
  return String(v);
}

function fromText(kind: Kind, s: string): unknown {
  if (kind === "qty") return s.split(/[,\s]+/).filter(Boolean).map(Number).filter((n) => n > 0);
  if (kind === "list") return s.split("\n").map((x) => x.trim()).filter(Boolean);
  return s.trim();
}

export function FlagList({ flags }: { flags: Flag[] }) {
  if (!flags.length) return <p className="muted small" style={{ margin: 0 }}>No flags. Claude found nothing to raise.</p>;
  const sorted = [...flags].sort((a, b) => SEV_RANK[a.severity] - SEV_RANK[b.severity]);
  return (
    <div>
      {sorted.map((f, i) => (
        <div className={`flag ${f.severity}`} key={i}>
          <span className="sev">{f.severity}</span>
          <div><div className="fld">{label(f.field)}</div>{f.message}</div>
        </div>
      ))}
    </div>
  );
}

function Row({ job, k, f, onJob, onEditForm }: {
  job: Job; k: string; f: Field; onJob: (j: Job) => void; onEditForm: () => void;
}) {
  const kind = kindOf(k, f);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const pending = f.source === "AI" && !f.approved;

  async function run(p: Promise<Job>) {
    setBusy(true); setErr(null);
    try { onJob(await p); setEditing(false); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <tr className={pending ? "pending" : ""}>
      <td className="fk">
        <div>{label(k)}</div>
        <span className={`tag ${f.source}`}>{f.source}</span>
        {f.source === "AI" && f.confidence != null && (
          <span className="conf" title={`Confidence ${Math.round(f.confidence * 100)}%`}><i style={{ width: `${f.confidence * 100}%` }} /></span>
        )}
      </td>
      <td className="fv">
        {editing ? (
          <>
            <textarea autoFocus value={text} onChange={(e) => setText(e.target.value)}
              rows={kind === "list" ? Math.max(3, text.split("\n").length + 1) : Math.max(2, Math.ceil(text.length / 80) + 1)} />
            <div className="hint">{kind === "list" ? "One item per line." : kind === "qty" ? "Comma separated." : "Saving marks this value as yours [ENG]."}</div>
          </>
        ) : (
          display(k, f.value)
        )}
        {f.note && !editing && <div className="fnote">{f.note}</div>}
        {err && <div className="alert error small" style={{ marginTop: 8 }}>{err}</div>}
      </td>
      <td className="fa">
        {editing ? (
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button className="btn sm ghost" onClick={() => setEditing(false)} disabled={busy}>Cancel</button>
            <button className="btn sm primary" disabled={busy} onClick={() => run(api.setValue(job.id, k, fromText(kind, text)))}>Save</button>
          </div>
        ) : (
          <div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
            {kind === "form" && <button className="btn sm ghost" onClick={onEditForm}>Edit in form</button>}
            {kind !== "form" && kind !== "readonly" && (
              <button className="btn sm" onClick={() => { setText(toText(kind, f.value)); setEditing(true); }}>Edit</button>
            )}
            {pending && <button className="btn sm primary" disabled={busy} onClick={() => run(api.approve(job.id, k))}>Approve</button>}
            {f.source === "AI" && f.approved && (
              <button className="btn sm ok" title="Click to un-approve" disabled={busy} onClick={() => run(api.approve(job.id, k, false))}>✓ Approved</button>
            )}
          </div>
        )}
      </td>
    </tr>
  );
}

export function ReviewView({ job, onJob, onEditForm }: { job: Job; onJob: (j: Job) => void; onEditForm: () => void }) {
  const groups: [string, string, string[]][] = [
    ["Drafted by Claude", "Approve or edit each one. Editing turns it into your value.", AI_ORDER],
    ["Your inputs", "From the part details form.", ENG_ORDER],
    ["Measured from CAD", "Read from the STEP file. Not editable.", CAD_ORDER],
  ];
  const seen = new Set<string>();
  return (
    <div className="stack">
      {groups.map(([title, sub, order]) => {
        const keys = order.filter((k) => {
          const f = job.fields[k];
          if (!f || seen.has(k)) return false;
          const src = title.startsWith("Drafted") ? f.source === "AI" || f.edited : title.startsWith("Your") ? f.source === "ENG" : f.source === "CAD";
          if (src) seen.add(k);
          return src;
        });
        if (!keys.length) return null;
        return (
          <div className="card" key={title}>
            <div className="card-head">
              <div><h3>{title}</h3><div className="small muted">{sub}</div></div>
            </div>
            <table className="ftable"><tbody>
              {keys.map((k) => <Row key={k + JSON.stringify(job.fields[k])} job={job} k={k} f={job.fields[k]} onJob={onJob} onEditForm={onEditForm} />)}
            </tbody></table>
          </div>
        );
      })}
    </div>
  );
}
