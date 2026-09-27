import type { JobStatus } from "@/lib/api";

const TEXT: Record<JobStatus, [string, string]> = {
  uploaded: ["Uploaded", ""],
  extracting: ["Reading CAD", ""],
  awaiting_form: ["Needs details", "warn"],
  drafting: ["Drafting", "ai"],
  review: ["In review", "ai"],
  rendering: ["Rendering", ""],
  done: ["PDF ready", "ok"],
  failed: ["Failed", "err"],
};

export function StatusPill({ status }: { status: JobStatus }) {
  const [t, c] = TEXT[status] || [status, ""];
  return <span className={`pill ${c}`}>{t}</span>;
}
