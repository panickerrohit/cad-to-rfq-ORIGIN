import Link from "next/link";
import { SITE_NAME } from "@/lib/site";

const STEPS = [
  { n: "01", t: "Upload the STEP file", d: "We read the solid: envelope, volume, surface area, and front, top, right and iso views." },
  { n: "02", t: "Answer one short form", d: "Material, tolerances, finish, quantities, dates, certs. The things CAD can't tell a supplier." },
  { n: "03", t: "Review Claude's draft", d: "Scope, process notes, inspection and quote questions, with flags for gaps and conflicts." },
  { n: "04", t: "Export the RFQ package", d: "Cover, spec sheet with vector views, requirements and a supplier quote form, as one PDF." },
];

const MOCK_ROWS: [string, string, "CAD" | "ENG" | "AI"][] = [
  ["Envelope", "80.0 × 60.0 × 68.0 mm", "CAD"],
  ["Material", "6061-T6 aluminum", "ENG"],
  ["Finish", "Type II clear anodize", "ENG"],
  ["Qty breaks", "25, 100, 500", "ENG"],
  ["Process", "CNC mill from plate; anodize after machining", "AI"],
  ["Inspection", "FAI; pilot bore 22.00 +0.05/-0 on every part", "AI"],
];

export default function Landing() {
  return (
    <main>
      <section className="hero">
        <div className="wrap hero-grid">
          <div>
            <div className="eyebrow">For mechanical engineers and buyers</div>
            <h1>
              From CAD file to <span className="hl">supplier-ready RFQ</span> in under 10 minutes.
            </h1>
            <p className="lead">
              Your STEP file already holds the geometry. {SITE_NAME} turns it, plus a one-screen form, into a complete
              RFQ package, and Claude flags what's missing before a supplier has to ask.
            </p>
            <div className="row">
              <Link href="/new" className="btn primary lg">Start an RFQ</Link>
              <a href="/samples/RFQ_Package_Sample_SB-1042.pdf" target="_blank" className="btn lg">See a sample PDF</a>
            </div>
            <p className="small faint" style={{ marginTop: 16 }}>No account needed for the pilot. STEP files up to 50 MB, one part per RFQ.</p>
          </div>
          <div className="card mock">
            <div className="row" style={{ marginBottom: 10 }}>
              <b>SB-1042 · Stepper Motor Bracket</b>
              <div className="spacer" />
              <span className="pill warn">1 flag</span>
            </div>
            {MOCK_ROWS.map(([k, v, s]) => (
              <div className="mock-row" key={k}>
                <span className="k">{k}</span>
                <span>{v}</span>
                <span className={`tag ${s}`}>{s}</span>
              </div>
            ))}
            <div className="flag warn" style={{ marginTop: 12 }}>
              <span className="sev">warn</span>
              <span>Packaging not specified; a default was proposed for you to confirm.</span>
            </div>
          </div>
        </div>
      </section>

      <section className="section" id="how">
        <div className="wrap">
          <div className="section-head">
            <h2>How it works</h2>
            <p>The gap between "design done" and "parts ordered" is mostly retyping. We automate the retyping and leave the judgement to you.</p>
          </div>
          <div className="steps">
            {STEPS.map((s) => (
              <div className="card step-card" key={s.n}>
                <div className="step-num">{s.n}</div>
                <h3>{s.t}</h3>
                <p>{s.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section alt" id="trust">
        <div className="wrap split">
          <div>
            <h2>Every value is traceable</h2>
            <p className="muted">
              Each line in the package is tagged by where it came from. Nothing reaches a supplier until you've approved it.
            </p>
            <div className="stack" style={{ marginTop: 20 }}>
              <div className="row"><span className="tag CAD">CAD</span><span>Measured from your STEP file.</span></div>
              <div className="row"><span className="tag ENG">ENG</span><span>Entered or edited by you.</span></div>
              <div className="row"><span className="tag AI">AI</span><span>Drafted by Claude. Needs your approval before export.</span></div>
            </div>
          </div>
          <div className="card card-pad">
            <h3>Your CAD stays yours</h3>
            <ul className="checklist">
              <li><b>Geometry never goes to the AI.</b> Claude sees extracted facts (sizes, volume) and your form, not the model.</li>
              <li><b>AI never overrides you.</b> It can add text and flags; it can't change a CAD or engineer value.</li>
              <li><b>No invented specs.</b> Anything missing becomes a question to the supplier or a flag to you.</li>
              <li><b>Supplier copy strips internals.</b> The provenance page and tags stay on your internal copy.</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="section" id="samples">
        <div className="wrap">
          <div className="section-head">
            <h2>What you get</h2>
            <p>A five-page package: cover, spec sheet with views, requirements, supplier quote form, and an internal provenance page.</p>
          </div>
          <div className="samples">
            <div className="card sample">
              <span className="pill">Machined part · STEP</span>
              <h3>SB-1042 stepper motor bracket</h3>
              <p>6061-T6, anodized, three quantity breaks, FAI and material certs.</p>
              <a className="btn" href="/samples/RFQ_Package_Sample_SB-1042.pdf" target="_blank">Open PDF</a>
            </div>
            <div className="card sample">
              <span className="pill">Finished product · DWG</span>
              <h3>OC-100 office chair</h3>
              <p>Built from a 2D catalogue drawing in three back heights. DWG input is on the roadmap after the MVP.</p>
              <a className="btn" href="/samples/RFQ_Package_Office_Chair_OC-100.pdf" target="_blank">Open PDF</a>
            </div>
          </div>
        </div>
      </section>

      <section className="section alt cta">
        <div className="wrap">
          <h2>Try it on a part you're quoting this week</h2>
          <p className="muted">No STEP file handy? Use our demo bracket and see the whole flow.</p>
          <Link href="/new" className="btn primary lg">Start an RFQ</Link>
        </div>
      </section>

      <footer className="footer">
        <div className="wrap row">
          <span>© {new Date().getFullYear()} {SITE_NAME}. Pilot version.</span>
          <div className="spacer" />
          <span>Built with Claude</span>
        </div>
      </footer>
    </main>
  );
}
