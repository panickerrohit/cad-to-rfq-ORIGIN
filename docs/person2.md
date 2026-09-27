# Person 2: AI draft + RFQ PDF

Lane B of the 2-day plan (`docs/Team_Work_Split_2Day.md`). Two pure functions plus a CLI:

| Function | In | Out |
|---|---|---|
| `app.ai.draft(cad_facts, eng_form)` | `cad_facts.json` + `eng_form.json` (dicts) | `draft.json` dict: 5 fields + flags |
| `app.pdf.render(fields, views_root=".")` | `fields.json` dict | RFQ package PDF as bytes |

The folder mirrors the repo layout: copy `api/app/ai/`, `api/app/pdf/`, `api/app/cli.py`, `api/fixtures/` and `api/tests/` into the repo's `api/`.

## Setup

Python 3.11.

```bash
cd api
pip install -r ../requirements.txt        # anthropic, pydantic, reportlab, pymupdf
export ANTHROPIC_API_KEY=sk-ant-...       # from the shared .env; never commit it or hardcode it
```

No key yet? Add `--mock` to any command (or `export DRAFT_MOCK=1`). The mock is rule-based: same JSON shape, a few conflict checks, no API call.

Model defaults to `claude-opus-5`. Override with `export CLAUDE_MODEL=claude-sonnet-5` (cheaper, what the dev manual suggested).

## Run (from `api/`)

```bash
# whole lane in one go: draft -> merge -> PDF (this is the demo fallback CLI)
python -m app.cli run fixtures/cad_facts.json fixtures/eng_form.json -o out/
python -m app.cli run fixtures/cad_facts.json fixtures/eng_form_conflict.json -o out_conflict/ --mock   # anodize-on-steel flag

# one step at a time
python -m app.cli draft  fixtures/cad_facts.json fixtures/eng_form.json -o out/draft.json
python -m app.cli merge  fixtures/cad_facts.json fixtures/eng_form.json out/draft.json -o out/fields.json
python -m app.cli render out/fields.json -o out/rfq.pdf

# once Person 1's app/cad/extract() exists, a STEP file works directly
python -m app.cli run demo.step form.json -o out/

# tests (no key needed; the Claude call is tested with a fake client)
pip install pytest && python -m pytest -q tests
```

`run` prints the flags and writes `cad_facts.json`, `draft.json`, `fields.json` and `RFQ_<part>.pdf` into the output folder.

## How it works

**Draft (`app/ai/draft.py`).** One `client.messages.parse(...)` call with `output_format=DraftOut` (Pydantic), so Claude's reply is forced into the exact `draft.json` shape. System prompt follows dev manual 5.4: use only given facts, turn anything missing into a supplier request or a flag, flag conflicts (anodize on steel, tight tolerances, missing packaging, quote due after delivery). One retry, then `DraftError` with a readable message. View file paths are stripped before sending. To tune flags for the demo, edit `SYSTEM_PROMPT`.

**Merge (`app/cli.py: merge`).** A stand-in for Person 3's review step so the CLI works alone: AI fields in, CAD and ENG fields override, all marked approved. The web app replaces it; the renderer only needs a valid `fields.json`.

**Render (`app/pdf/render.py`).** Port of `samples/src/rfq.py`, now reading every value from `fields.json`. Views use the `Slot` + `show_pdf_page` stamping from `rfq_chair.py`: four boxes on page 2 (front, top, right, iso), each filled with the view PDF at `views[].key` (resolved as given, then relative to `views_root`). A missing view prints "View not available" instead of crashing; so does any missing field ("Not specified").

Pages: 1 cover, 2 spec sheet + views, 3 requirements, 4 supplier quote form, 5 internal provenance page with flags and every field's source.

`options` in `fields.json`:

| Key | Default | Effect |
|---|---|---|
| `page_size` | letter if buyer country is US/CA/MX, else A4 | `"letter"` or `"a4"` |
| `include_internal_page` | `true` | page 5 on/off (off for the supplier copy) |
| `show_tags` | `true` | `[CAD]` / `[ENG]` / `[AI]` tags on/off |

Optional fields the renderer reads if present: `rfq_number`, `issue_date`, `incoterms`, `payment_terms`, `source_filename`, `notes`.

## Fixtures

`api/fixtures/`: `cad_facts.json`, `eng_form.json`, `eng_form_conflict.json` (steel + anodize), `draft.json`, `fields.json`, and `views/*.pdf` (fake L-bracket views; regenerate with `python fixtures/make_fixture_views.py`). Contracts match `docs/Team_Work_Split.md` minus `hole_candidates`, `dimension_labels` and the approval flag, per the 2-day cuts.

`sample_output/` has PDFs rendered from the fixtures in mock mode.
