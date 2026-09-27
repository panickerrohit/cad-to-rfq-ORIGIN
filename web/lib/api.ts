// Typed client for the FastAPI backend (api/app/main.py).
// Calls go to /api/* and are proxied by next.config.ts, unless NEXT_PUBLIC_API_URL is set.

export const API = process.env.NEXT_PUBLIC_API_URL || "/api";

export type Source = "CAD" | "ENG" | "AI";

export type Field = {
  value: unknown;
  source: Source;
  confidence: number | null;
  note: string;
  approved: boolean;
  edited?: boolean;
};

export type Flag = { severity: "info" | "warn" | "error"; field: string; message: string };

export type CriticalDim = { feature: string; value: string; unit?: string };
export type Buyer = { company: string; contact?: string; email?: string; country?: string };

export type EngForm = {
  part_name: string;
  part_number: string;
  revision: string;
  material: string;
  general_tolerance: string;
  critical_dims: CriticalDim[];
  finish: string;
  qty_breaks: number[];
  target_delivery: string;
  certs: string[];
  packaging: string | null;
  buyer: Buyer;
  quote_due: string | null;
  notes: string;
};

export type CadFacts = {
  source: { filename: string; type: string; units: string };
  bbox_mm: { x: number; y: number; z: number } | null;
  volume_mm3: number | null;
  surface_area_mm2: number | null;
  solid_count: number | null;
  is_assembly: boolean;
  warnings: string[];
};

export type JobStatus =
  | "uploaded" | "extracting" | "awaiting_form" | "drafting" | "review" | "rendering" | "done" | "failed";

export type Job = {
  id: string;
  status: JobStatus;
  created_at: string;
  cad_filename: string;
  cad_facts: CadFacts | null;
  form: (EngForm & { schema_version?: string }) | null;
  fields: Record<string, Field>;
  flags: Flag[];
  views: { name: string; url: string }[];
  error: string | null;
  pdf: string | null;
  pdf_url: string | null;
  pdf_supplier_copy?: boolean;
  draft_mode: "claude" | "mock" | null;
  unapproved: string[];
  working: boolean;
};

export type JobSummary = { id: string; status: JobStatus; filename: string; part_number: string | null; created_at: string };

export class ApiError extends Error {}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API + path, { cache: "no-store", ...init });
  } catch {
    throw new ApiError("Can't reach the API server. Is it running on port 8000?");
  }
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
      else if (Array.isArray(body.detail)) msg = body.detail.map((d: { loc?: string[]; msg: string }) =>
        `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ");
    } catch { /* not JSON */ }
    throw new ApiError(msg);
  }
  return res.json() as Promise<T>;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  health: () => call<{ ok: boolean; draft_mode: "claude" | "mock"; cadquery: boolean }>("/health"),
  listJobs: () => call<JobSummary[]>("/jobs"),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return call<Job>("/jobs", { method: "POST", body: fd });
  },
  demo: () => call<Job>("/jobs/demo", { method: "POST" }),
  demoForm: () => call<EngForm>("/demo/form"),
  get: (id: string) => call<Job>(`/jobs/${id}`),
  saveForm: (id: string, form: EngForm) => call<Job>(`/jobs/${id}/form`, json("PUT", form)),
  setValue: (id: string, key: string, value: unknown) =>
    call<Job>(`/jobs/${id}/fields/${key}`, json("PATCH", { value })),
  approve: (id: string, key: string, approved = true) =>
    call<Job>(`/jobs/${id}/fields/${key}`, json("PATCH", { approved })),
  approveAll: (id: string) => call<Job>(`/jobs/${id}/approve-all`, json("POST")),
  render: (id: string, supplier_copy: boolean) => call<Job>(`/jobs/${id}/render`, json("POST", { supplier_copy })),
  url: (path: string) => API + path,
};

// ---- display helpers shared by the review screen

export const LABELS: Record<string, string> = {
  part_name: "Part name", part_number: "Part number", revision: "Revision", material: "Material",
  general_tolerance: "General tolerance", critical_dims: "Critical dimensions", finish: "Finish",
  qty_breaks: "Quantity breaks", target_delivery: "Target delivery", certs: "Certifications",
  packaging: "Packaging", buyer: "Buyer", quote_due: "Quote due", notes: "Notes",
  bbox_mm: "Envelope (bounding box)", volume_mm3: "Volume", surface_area_mm2: "Surface area",
  solid_count: "Solid count", source_filename: "Source file",
  scope_of_work: "Scope of work", process_notes: "Process notes",
  inspection_requirements: "Inspection requirements", quote_form_questions: "Quote form questions",
};

export function label(key: string) {
  return LABELS[key] || key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

export function display(key: string, v: unknown): string {
  if (v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0)) return "Not specified";
  if (key === "volume_mm3" && typeof v === "number") return `${(v / 1000).toFixed(1)} cm³ (${v.toLocaleString()} mm³)`;
  if (key === "surface_area_mm2" && typeof v === "number") return `${v.toLocaleString()} mm²`;
  if (typeof v === "object" && !Array.isArray(v)) {
    const o = v as Record<string, unknown>;
    if ("x" in o && "y" in o && "z" in o) return `${Number(o.x).toFixed(1)} × ${Number(o.y).toFixed(1)} × ${Number(o.z).toFixed(1)} mm`;
    return Object.values(o).filter((x) => x !== null && x !== "").join(", ");
  }
  if (Array.isArray(v)) {
    if (v.length && typeof v[0] === "object") {
      return (v as CriticalDim[]).map((d) => `${d.feature}: ${d.value}${d.unit ? " " + d.unit : ""}`).join("\n");
    }
    return key === "qty_breaks" ? v.join(", ") : v.map(String).join("\n");
  }
  return String(v);
}
