"""Claude drafting step (Lane B).

draft(cad_facts, eng_form) -> dict matching the draft.json contract:

    {"schema_version": "1",
     "fields": {"scope_of_work": {"value", "confidence", "note"}, ...},
     "flags": [{"severity", "field", "message"}, ...]}

One Claude call with structured output (JSON schema from the Pydantic models
below), so the reply is always valid JSON in this exact shape. If the call
fails validation it is retried once, then DraftError is raised.

Set DRAFT_MOCK=1 (or pass mock=True) to skip the API and use the rule-based
mock in mock.py. Useful with no API key, and as the demo fallback.
"""
from __future__ import annotations

import json
import os
from typing import List, Literal, Optional

from pydantic import BaseModel, ValidationError

DEFAULT_MODEL = "claude-opus-5"

SYSTEM_PROMPT = """You draft the text sections of a Request for Quotation (RFQ) package that a \
mechanical engineer will send to machine shops and other manufacturing suppliers.

You receive one JSON object with two keys:
- "cad": facts measured from the part's STEP file (bounding box, volume, surface area, solid count, warnings).
- "eng": what the engineer entered (part name/number, material, tolerances, finish, quantities, dates, certs, buyer).

Rules:
1. Use only the given facts. Never invent dimensions, tolerances, thread sizes, material specs, or certifications.
2. Anything the RFQ needs that is not in "cad" or "eng" must be written as a request to the supplier \
("Supplier to propose ...", "Quote ... separately") or raised as a flag. Never state it as fact.
3. Flag conflicts and risks you can see in the inputs, for example: anodize specified on steel or another \
non-aluminum material; a tolerance too tight for the likely process or part size; quantity that does not fit \
the implied process (e.g. qty 10 with injection molding); missing thread spec, finish, material, or packaging; \
quote due date after or too close to the delivery date; CAD warnings (units, multiple solids).
4. Plain procurement English. Short sentences. No marketing language.
5. For each field give a confidence from 0 to 1 and a short note saying which inputs it came from \
or what you assumed. Leave the note empty if there is nothing to say.

Fields to produce:
- scope_of_work: 2 to 4 sentences. What the supplier supplies and what the quote must cover (each qty break, NRE on its own line).
- process_notes: likely manufacturing route, phrased as a suggestion, and any process-related requests.
- inspection_requirements: what to inspect and what documents to ship, from the critical dims and certs.
- packaging: use eng.packaging if given; otherwise propose a sensible default and flag it.
- quote_form_questions: 3 to 6 short questions the supplier should answer on the quote form.

Flags: severity is "error" for a conflict that makes the RFQ wrong, "warn" for a gap or risk the engineer \
should fix, "info" for something to confirm. "field" names the input or output field concerned."""


class TextField(BaseModel):
    value: str
    confidence: float
    note: str


class ListField(BaseModel):
    value: List[str]
    confidence: float
    note: str


class DraftFields(BaseModel):
    scope_of_work: TextField
    process_notes: TextField
    inspection_requirements: TextField
    packaging: TextField
    quote_form_questions: ListField


class Flag(BaseModel):
    severity: Literal["info", "warn", "error"]
    field: str
    message: str


class DraftOut(BaseModel):
    fields: DraftFields
    flags: List[Flag]


class DraftError(RuntimeError):
    pass


def _to_contract(d: DraftOut) -> dict:
    out = {"schema_version": "1", **d.model_dump()}
    for f in out["fields"].values():  # clamp; the schema can't enforce ranges
        f["confidence"] = max(0.0, min(1.0, float(f["confidence"])))
    return out


def draft(cad_facts: dict, eng_form: dict, *, model: Optional[str] = None,
          mock: Optional[bool] = None, client=None) -> dict:
    """CAD facts + engineer form in, draft.json dict out."""
    if mock is None:
        mock = os.environ.get("DRAFT_MOCK", "").lower() in ("1", "true", "yes")
    if mock:
        from .mock import mock_draft
        return _to_contract(DraftOut.model_validate(mock_draft(cad_facts, eng_form)))

    import anthropic

    client = client or anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    model = model or os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)
    # Views are file keys, not facts; keep them out of the prompt.
    cad = {k: v for k, v in cad_facts.items() if k != "views"}
    user = json.dumps({"cad": cad, "eng": eng_form}, indent=2, ensure_ascii=False)

    last_err = None
    for _ in range(2):  # one retry
        try:
            resp = client.messages.parse(
                model=model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user}],
                output_format=DraftOut,
            )
        except anthropic.APIStatusError as e:
            if e.status_code in (400, 401, 403, 404):
                raise DraftError(f"Claude API error {e.status_code}: {e.message}") from e
            last_err = e
            continue
        except TypeError as e:  # raised by the SDK when no credentials are configured
            raise DraftError("No Anthropic credentials. Set ANTHROPIC_API_KEY, or use --mock / DRAFT_MOCK=1.") from e
        except (anthropic.APIConnectionError, ValidationError) as e:
            last_err = e
            continue
        if resp.stop_reason == "refusal":
            raise DraftError("Claude declined to draft this RFQ (stop_reason=refusal).")
        if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
            last_err = DraftError(f"Unusable response (stop_reason={resp.stop_reason}).")
            continue
        return _to_contract(resp.parsed_output)
    raise DraftError(f"Drafting failed after retry: {last_err}")
