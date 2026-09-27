# CAD to RFQ: MVP website

The full MVP from `docs/MVP_Developer_Manual.md`: landing page, STEP upload, engineer form, Claude draft with `[CAD]` / `[ENG]` / `[AI]` provenance and flags, review screen, and RFQ package PDF export. Built on the 2-day plan's cuts (no database, queue or auth; jobs are folders on disk).

```
website/
  dev.sh            starts api + web together
  api/              FastAPI (Python 3.11)
    app/main.py     routes (dev manual section 6)
    app/jobs.py     job store + pipeline: extract -> draft -> merge -> render
    app/cad/        Lane A: STEP -> facts + front/top/right/iso vector views (CadQuery)
    app/ai/         Lane B: Claude draft (from code/person2, unchanged)
    app/pdf/        Lane B: RFQ PDF renderer (from code/person2, unchanged)
    app/cli.py      demo fallback CLI (from code/person2)
    fixtures/       contract JSONs + step/SB-1042_RevA.step demo part
    tests/          pytest: Lane B smoke tests + full API flow
  web/              Next.js 16 (App Router, TypeScript, plain CSS)
    app/page.tsx          landing
    app/new/page.tsx      upload + recent RFQs
    app/jobs/[id]/page.tsx  form -> review -> export, one page per job
```

## Run it locally

Needs Python 3.11 and Node 20+.

```bash
# 1. API
cd api
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...     # optional; without it drafts use the rule-based mock
python -m pytest -q tests               # 8 tests, no key needed
uvicorn app.main:app --reload --port 8000

# 2. Web (second terminal)
cd web
npm install
npm run dev                              # http://localhost:3000
```

Or run `./dev.sh` from this folder to start both (it reads `api/.env` if present; see `api/.env.example`).

The web app calls `/api/*`, which Next forwards to `http://127.0.0.1:8000` (set `API_URL` to point elsewhere). Open http://localhost:3000, click **New RFQ**, and either upload a STEP file or click **Use the demo bracket**.

## What happens in a job

1. **Upload** `POST /jobs`: file saved to `api/jobs/<id>/`, extraction runs in the background.
2. **Extract** (`app/cad/extract.py`): CadQuery reads the solid; bbox, volume, area, solid count, units sanity check, 4 SVG views converted to vector PDF. More than one solid is rejected with a clear message.
3. **Form** `PUT /jobs/{id}/form`: part number and rev are pre-filled from the filename (`SB-1042_RevA.step`).
4. **Draft**: one Claude call (`claude-opus-5` by default, `CLAUDE_MODEL` to change) returns scope, process notes, inspection, packaging, quote questions and flags. AI fields are merged under CAD and ENG values, never over them.
5. **Review**: every field shows its source tag, note and confidence. Edit flips a field to `[ENG]`. Export stays disabled until every AI field is approved or edited (`409` from the API otherwise).
6. **Export** `POST /jobs/{id}/render`: 5-page PDF with the real views stamped in. Tick **Supplier copy** to drop the tags and the internal provenance page.

## Good to know

- **No API key** means the draft comes from `app/ai/mock.py` and the review screen shows a "Demo mode" banner. `GET /health` reports which mode is live.
- **No CadQuery** (it's a heavy install): the API still runs. A text fallback reads the bounding box and units straight from the STEP file and warns that volume, area and views are unavailable. The PDF shows "View not available" in the view boxes.
- **Product name** is a placeholder ("Drafted"), set in `web/lib/site.ts`.
- **CLI fallback** for demos still works: `cd api && python -m app.cli run fixtures/step/SB-1042_RevA.step fixtures/eng_form.json -o out/`.
- **Regenerate the demo part**: `python fixtures/make_demo_step.py`.

## Not in this build (per the 2-day cuts)

DWG input, accounts/auth, Postgres/Redis/worker queue, deployment config, file expiry. Jobs live in `api/jobs/` until you delete them. For a public demo, run locally and share with a tunnel (`cloudflared tunnel --url http://localhost:3000`).
