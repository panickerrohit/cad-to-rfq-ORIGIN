"""Job store and pipeline for the web app.

Per the 2-day plan there is no database or queue: each job is a folder
./jobs/<id>/ holding job.json, the uploaded CAD file, views/ and the PDF.
Heavy steps run in FastAPI BackgroundTasks.

Status flow (dev manual section 4):
    uploaded -> extracting -> awaiting_form -> drafting -> review -> rendering -> done
    any step can go to failed (job["error"] says why)

Every value the PDF prints is a Field {value, source, confidence, note, approved}.
AI never overwrites CAD or ENG fields; editing an AI field flips it to ENG.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import uuid

from .ai import DraftError, draft
from .cad import CadError, extract
from .pdf import render

JOBS_DIR = os.path.abspath(os.environ.get("JOBS_DIR", os.path.join(os.path.dirname(__file__), "..", "jobs")))
FIXTURES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures"))

CAD_KEYS = ["bbox_mm", "volume_mm3", "surface_area_mm2", "solid_count", "source_filename"]
ENG_KEYS = ["part_name", "part_number", "revision", "material", "general_tolerance", "critical_dims", "finish",
            "qty_breaks", "target_delivery", "certs", "packaging", "buyer", "quote_due", "notes"]
AI_KEYS = ["scope_of_work", "process_notes", "inspection_requirements", "packaging", "quote_form_questions"]
WORKING = {"uploaded", "extracting", "drafting", "rendering"}

_lock = threading.Lock()


class JobNotFound(KeyError):
    pass


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def job_dir(job_id: str) -> str:
    try:
        uuid.UUID(job_id)
    except ValueError as e:
        raise JobNotFound(job_id) from e
    return os.path.join(JOBS_DIR, job_id)


def load(job_id: str) -> dict:
    p = os.path.join(job_dir(job_id), "job.json")
    if not os.path.isfile(p):
        raise JobNotFound(job_id)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(job: dict) -> dict:
    job["updated_at"] = now()
    d = job_dir(job["id"])
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, "job.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(job, f, indent=2, ensure_ascii=False)
    os.replace(tmp, os.path.join(d, "job.json"))
    return job


def update(job_id: str, **changes) -> dict:
    with _lock:
        job = load(job_id)
        job.update(changes)
        return save(job)


def list_jobs(limit=20) -> list[dict]:
    if not os.path.isdir(JOBS_DIR):
        return []
    out = []
    for name in os.listdir(JOBS_DIR):
        try:
            j = load(name)
        except (JobNotFound, json.JSONDecodeError):
            continue
        part = ((j.get("fields") or {}).get("part_number") or {}).get("value") or (j.get("form") or {}).get("part_number")
        out.append({"id": j["id"], "status": j["status"], "filename": j.get("cad_filename"),
                    "part_number": part, "created_at": j.get("created_at")})
    return sorted(out, key=lambda j: j["created_at"] or "", reverse=True)[:limit]


def create(filename: str, data: bytes) -> dict:
    job_id = str(uuid.uuid4())
    d = job_dir(job_id)
    os.makedirs(d, exist_ok=True)
    safe = os.path.basename(filename or "upload.step").replace(" ", "_") or "upload.step"
    with open(os.path.join(d, safe), "wb") as f:
        f.write(data)
    job = {"id": job_id, "status": "uploaded", "created_at": now(), "cad_filename": safe, "cad_type": "step",
           "cad_facts": None, "form": None, "draft": None, "fields": {}, "flags": [], "views": [],
           "error": None, "pdf": None, "draft_mode": None}
    return save(job)


# ------------------------------------------------------------------ pipeline steps
def run_extract(job_id: str):
    job = update(job_id, status="extracting", error=None)
    d = job_dir(job_id)
    try:
        facts = extract(os.path.join(d, job["cad_filename"]), os.path.join(d, "views"))
    except CadError as e:
        update(job_id, status="failed", error=str(e))
        return
    except Exception as e:  # never leave a job stuck in "extracting"
        update(job_id, status="failed", error=f"CAD extraction crashed: {e}")
        return
    # store view keys relative to the job folder so the folder can move
    views = [{"name": v["name"], "key": os.path.relpath(v["key"], d)} for v in facts.get("views", [])]
    facts["views"] = views
    fields = cad_fields(facts)
    update(job_id, status="awaiting_form", cad_facts=facts, views=views, fields=fields)


def cad_fields(facts: dict) -> dict:
    notes = {"bbox_mm": "Overall envelope from the STEP solid", "volume_mm3": "Solid volume from STEP",
             "surface_area_mm2": "Total surface area from STEP", "solid_count": "Solids in the STEP file",
             "source_filename": "Uploaded file"}
    vals = dict(facts)
    vals["source_filename"] = (facts.get("source") or {}).get("filename")
    return {k: {"value": vals[k], "source": "CAD", "confidence": None, "note": notes[k], "approved": True}
            for k in CAD_KEYS if vals.get(k) is not None}


def draft_mode() -> str:
    if os.environ.get("DRAFT_MOCK", "").lower() in ("1", "true", "yes"):
        return "mock"
    return "claude" if os.environ.get("ANTHROPIC_API_KEY") else "mock"


def run_draft(job_id: str):
    job = update(job_id, status="drafting", error=None)
    mode = draft_mode()
    try:
        drf = draft(job["cad_facts"] or {}, job["form"] or {}, mock=(mode == "mock"))
    except DraftError as e:
        update(job_id, status="failed", error=str(e))
        return
    except Exception as e:
        update(job_id, status="failed", error=f"Drafting crashed: {e}")
        return
    with _lock:
        job = load(job_id)
        job["draft"], job["draft_mode"] = drf, mode
        job["fields"] = merge_fields(job["cad_facts"] or {}, job["form"] or {}, drf, job.get("fields") or {})
        job["flags"] = drf.get("flags", [])
        job["status"] = "review"
        save(job)


def merge_fields(cad: dict, eng: dict, drf: dict, previous: dict) -> dict:
    """AI first, then CAD and ENG on top: AI never overwrites CAD or ENG."""
    fields = {}
    for k, e in (drf.get("fields") or {}).items():
        fields[k] = {"value": e["value"], "source": "AI", "confidence": e.get("confidence"),
                     "note": e.get("note") or "", "approved": False}
    fields.update(cad_fields(cad))
    for k in ENG_KEYS:
        if eng.get(k) not in (None, "", [], {}):
            fields[k] = {"value": eng[k], "source": "ENG", "confidence": None, "note": "Entered by engineer",
                         "approved": True}
    # keep manual edits made on an earlier review pass of this job
    for k, f in previous.items():
        if f.get("edited"):
            fields[k] = f
    return fields


def edit_field(job_id: str, key: str, value=None, approved: bool | None = None, set_value: bool = False) -> dict:
    with _lock:
        job = load(job_id)
        f = job["fields"].get(key)
        if f is None:
            f = {"value": None, "source": "ENG", "confidence": None, "note": "", "approved": True}
            job["fields"][key] = f
        if set_value:
            f["value"] = value
            if f["source"] == "AI":
                f["note"] = (f.get("note") + " · " if f.get("note") else "") + "Edited by engineer"
            f["source"], f["approved"], f["edited"] = "ENG", True, True
        if approved is not None:
            f["approved"] = bool(approved)
        if job["status"] == "done":  # PDF is stale now
            job["status"], job["pdf"] = "review", None
        return save(job)


def unapproved(job: dict) -> list[str]:
    return [k for k, f in job["fields"].items() if f["source"] == "AI" and not f.get("approved")]


def fields_json(job: dict, supplier_copy: bool = False) -> dict:
    return {"schema_version": "1", "job_id": job["id"], "fields": job["fields"], "flags": job["flags"],
            "views": job["views"],
            "options": {"include_internal_page": not supplier_copy, "show_tags": not supplier_copy}}


def run_render(job_id: str, supplier_copy: bool = False):
    job = update(job_id, status="rendering", error=None)
    try:
        pdf = render(fields_json(job, supplier_copy), views_root=job_dir(job_id))
    except Exception as e:
        update(job_id, status="failed", error=f"PDF render failed: {e}")
        return
    pn = str((job["fields"].get("part_number") or {}).get("value") or "part")
    name = "RFQ_" + "".join(c if c.isalnum() or c in "-_." else "_" for c in pn) + ("_supplier" if supplier_copy else "") + ".pdf"
    with open(os.path.join(job_dir(job_id), name), "wb") as f:
        f.write(pdf)
    update(job_id, status="done", pdf=name, pdf_supplier_copy=supplier_copy, rendered_at=now())


def create_demo() -> dict:
    """A job pre-loaded with the demo bracket STEP, for people without a file to hand."""
    p = os.path.join(FIXTURES, "step", "SB-1042_RevA.step")
    with open(p, "rb") as f:
        return create("SB-1042_RevA.step", f.read())


def demo_form() -> dict:
    with open(os.path.join(FIXTURES, "eng_form.json"), encoding="utf-8") as f:
        return json.load(f)
