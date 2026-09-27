"use client";

import { useEffect, useState } from "react";
import { api, CriticalDim, EngForm, Job } from "@/lib/api";

const MATERIALS = [
  "6061-T6 aluminum", "7075-T6 aluminum", "5052-H32 aluminum sheet", "304 stainless steel", "316 stainless steel",
  "1018 steel", "4140 steel", "A36 steel", "Brass C360", "Acetal (POM)", "Nylon 6/6", "ABS", "Polycarbonate",
];
const FINISHES = [
  "As machined", "Bead blast", "Type II clear anodize", "Type II black anodize", "Type III hard anodize",
  "Zinc plate", "Black oxide", "Powder coat", "Passivate",
];
const TOLERANCES = ["ISO 2768-f", "ISO 2768-m", "ISO 2768-c", "ISO 2768-v", "±0.1 mm", "±0.05 mm"];
const CERTS = ["CoC", "material cert", "FAI", "RoHS", "REACH", "PPAP"];

function fromFilename(name: string): Partial<EngForm> {
  const stem = name.replace(/\.(step|stp)$/i, "");
  const m = stem.match(/^(.*?)[_\- ]?rev[_\- ]?([A-Za-z0-9]+)$/i);
  return m ? { part_number: m[1], revision: m[2].toUpperCase() } : { part_number: stem };
}

function inDays(n: number) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

function initial(job: Job): EngForm {
  if (job.form) {
    const { schema_version: _, ...f } = job.form;
    return { ...f, finish: f.finish || "", notes: f.notes || "", packaging: f.packaging ?? null };
  }
  return {
    part_name: "", part_number: "", revision: "A", material: "", general_tolerance: "ISO 2768-m",
    critical_dims: [], finish: "", qty_breaks: [], target_delivery: inDays(42), certs: ["CoC"],
    packaging: null, buyer: { company: "", contact: "", email: "", country: "US" }, quote_due: inDays(14), notes: "",
    ...fromFilename(job.cad_filename),
  };
}

export function EngFormView({ job, onSaved, onCancel }: { job: Job; onSaved: (j: Job) => void; onCancel?: () => void }) {
  const [f, setF] = useState<EngForm>(() => initial(job));
  const [qty, setQty] = useState(() => initial(job).qty_breaks.join(", "));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = <K extends keyof EngForm>(k: K, v: EngForm[K]) => setF((p) => ({ ...p, [k]: v }));
  const setBuyer = (k: keyof EngForm["buyer"], v: string) => setF((p) => ({ ...p, buyer: { ...p.buyer, [k]: v } }));
  const setDim = (i: number, k: keyof CriticalDim, v: string) =>
    setF((p) => ({ ...p, critical_dims: p.critical_dims.map((d, j) => (j === i ? { ...d, [k]: v } : d)) }));

  async function fillDemo() {
    try {
      const d = await api.demoForm();
      const { schema_version: _, ...rest } = d as EngForm & { schema_version?: string };
      setF({ ...rest, finish: rest.finish || "", notes: rest.notes || "" });
      setQty(rest.qty_breaks.join(", "));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    // "Use the demo bracket" lands here with ?demo=1: pre-fill the matching demo answers.
    if (!job.form && window.location.search.includes("demo=1")) fillDemo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const qty_breaks = qty.split(/[,\s]+/).filter(Boolean).map(Number);
    if (!qty_breaks.length || qty_breaks.some((q) => !Number.isInteger(q) || q <= 0)) {
      setError("Quantity breaks must be whole numbers above zero, e.g. 25, 100, 500.");
      return;
    }
    if (f.quote_due && f.target_delivery && f.quote_due > f.target_delivery) {
      setError("The quote due date is after the target delivery date.");
      return;
    }
    setBusy(true);
    try {
      const job2 = await api.saveForm(job.id, { ...f, qty_breaks, packaging: f.packaging?.trim() || null });
      onSaved(job2);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <div className="card-head">
        <h2>Part details</h2>
        <div className="spacer" />
        <button type="button" className="btn sm ghost" onClick={fillDemo}>Fill demo values</button>
      </div>
      <div className="card-pad stack">
        <p className="muted small" style={{ margin: 0 }}>
          CAD gives us geometry only. These answers go into the RFQ as <span className="tag ENG">ENG</span> values and
          Claude never overrides them.
        </p>

        <div>
          <div className="section-title">Part</div>
          <div className="grid4">
            <label className="field span2"><span>Part name<em>*</em></span>
              <input required value={f.part_name} onChange={(e) => set("part_name", e.target.value)} placeholder="Stepper motor bracket" /></label>
            <label className="field"><span>Part number<em>*</em></span>
              <input required value={f.part_number} onChange={(e) => set("part_number", e.target.value)} /></label>
            <label className="field"><span>Revision<em>*</em></span>
              <input required value={f.revision} onChange={(e) => set("revision", e.target.value)} /></label>
          </div>
        </div>

        <div>
          <div className="section-title">Spec</div>
          <div className="grid3">
            <label className="field"><span>Material<em>*</em></span>
              <input required list="materials" value={f.material} onChange={(e) => set("material", e.target.value)} placeholder="6061-T6 aluminum" />
              <datalist id="materials">{MATERIALS.map((m) => <option key={m} value={m} />)}</datalist></label>
            <label className="field"><span>General tolerance<em>*</em></span>
              <input required list="tols" value={f.general_tolerance} onChange={(e) => set("general_tolerance", e.target.value)} />
              <datalist id="tols">{TOLERANCES.map((m) => <option key={m} value={m} />)}</datalist></label>
            <label className="field"><span>Finish</span>
              <input list="finishes" value={f.finish} onChange={(e) => set("finish", e.target.value)} placeholder="Type II clear anodize" />
              <datalist id="finishes">{FINISHES.map((m) => <option key={m} value={m} />)}</datalist></label>
          </div>
        </div>

        <div>
          <div className="section-title">Critical dimensions <span className="faint" style={{ textTransform: "none", letterSpacing: 0, fontWeight: 500 }}>(optional)</span></div>
          {f.critical_dims.map((d, i) => (
            <div className="dims-row" key={i}>
              <input value={d.feature} onChange={(e) => setDim(i, "feature", e.target.value)} placeholder="Feature, e.g. Pilot bore" />
              <input value={d.value} onChange={(e) => setDim(i, "value", e.target.value)} placeholder="22.00 +0.05/-0" />
              <input value={d.unit || ""} onChange={(e) => setDim(i, "unit", e.target.value)} placeholder="mm" />
              <button type="button" className="btn sm ghost" aria-label="Remove"
                onClick={() => set("critical_dims", f.critical_dims.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
          <button type="button" className="btn sm" onClick={() => set("critical_dims", [...f.critical_dims, { feature: "", value: "", unit: "mm" }])}>
            + Add dimension
          </button>
        </div>

        <div>
          <div className="section-title">Commercial</div>
          <div className="grid3">
            <label className="field"><span>Quantity breaks<em>*</em></span>
              <input required value={qty} onChange={(e) => setQty(e.target.value)} placeholder="25, 100, 500" />
              <div className="hint">Comma separated</div></label>
            <label className="field"><span>Quote due</span>
              <input type="date" value={f.quote_due || ""} onChange={(e) => set("quote_due", e.target.value || null)} /></label>
            <label className="field"><span>Target delivery<em>*</em></span>
              <input required type="date" value={f.target_delivery} onChange={(e) => set("target_delivery", e.target.value)} /></label>
          </div>
          <div style={{ marginTop: 14 }}>
            <label className="field"><span>Certifications and documents</span></label>
            <div className="checks">
              {CERTS.map((c) => (
                <label key={c}>
                  <input type="checkbox" checked={f.certs.includes(c)}
                    onChange={(e) => set("certs", e.target.checked ? [...f.certs, c] : f.certs.filter((x) => x !== c))} />
                  {c}
                </label>
              ))}
            </div>
          </div>
          <div className="grid2" style={{ marginTop: 14 }}>
            <label className="field"><span>Packaging</span>
              <input value={f.packaging || ""} onChange={(e) => set("packaging", e.target.value)} placeholder="Leave blank and Claude will propose one" /></label>
            <label className="field"><span>Notes to supplier</span>
              <input value={f.notes} onChange={(e) => set("notes", e.target.value)} /></label>
          </div>
        </div>

        <div>
          <div className="section-title">Buyer</div>
          <div className="grid4">
            <label className="field"><span>Company<em>*</em></span>
              <input required value={f.buyer.company} onChange={(e) => setBuyer("company", e.target.value)} /></label>
            <label className="field"><span>Contact</span>
              <input value={f.buyer.contact || ""} onChange={(e) => setBuyer("contact", e.target.value)} /></label>
            <label className="field"><span>Email</span>
              <input type="email" value={f.buyer.email || ""} onChange={(e) => setBuyer("email", e.target.value)} /></label>
            <label className="field"><span>Country</span>
              <input value={f.buyer.country || ""} maxLength={2} onChange={(e) => setBuyer("country", e.target.value.toUpperCase())} placeholder="US" />
              <div className="hint">US/CA/MX get Letter, others A4</div></label>
          </div>
        </div>

        {error && <div className="alert error">{error}</div>}
        <div className="row">
          {onCancel && <button type="button" className="btn" onClick={onCancel}>Back to review</button>}
          <div className="spacer" />
          <button type="submit" className="btn primary lg" disabled={busy}>{busy ? "Sending…" : "Draft the RFQ"}</button>
        </div>
      </div>
    </form>
  );
}
