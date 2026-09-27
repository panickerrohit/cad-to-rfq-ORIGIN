import { api, display, Job } from "@/lib/api";

// Left/side panel: what we measured from the STEP file.
export function CadPanel({ job, compact = false }: { job: Job; compact?: boolean }) {
  const f = job.cad_facts;
  if (!f) return null;
  const facts: [string, string][] = [
    ["Envelope", display("bbox_mm", f.bbox_mm)],
    ["Volume", f.volume_mm3 == null ? "Not available" : `${(f.volume_mm3 / 1000).toFixed(1)} cm³`],
    ["Surface area", f.surface_area_mm2 == null ? "Not available" : `${Math.round(f.surface_area_mm2).toLocaleString()} mm²`],
    ["Solids", f.solid_count == null ? "Unknown" : String(f.solid_count)],
  ];
  const notes = f.warnings.filter((w) => w !== "Units look plausible");
  return (
    <div className="card card-pad">
      <div className="row" style={{ marginBottom: 12 }}>
        <h3 style={{ margin: 0 }}>From your CAD</h3>
        <div className="spacer" />
        <span className="tag CAD">CAD</span>
      </div>
      <p className="mono small muted" style={{ marginBottom: 12, wordBreak: "break-all" }}>{f.source.filename}</p>
      {job.views.length > 0 && (
        <div className="views" style={{ marginBottom: 14 }}>
          {job.views.map((v) => (
            <div className="view" key={v.name}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={api.url(v.url)} alt={`${v.name} view`} />
              <span>{v.name}</span>
            </div>
          ))}
        </div>
      )}
      <div className="facts">
        {facts.map(([k, v]) => (
          <div className="fact" key={k}><div className="k">{k}</div><div className="v">{v}</div></div>
        ))}
      </div>
      {!compact && notes.length > 0 && (
        <div style={{ marginTop: 14 }}>
          {notes.map((w) => <div key={w} className="small muted" style={{ marginTop: 4 }}>• {w}</div>)}
        </div>
      )}
    </div>
  );
}
