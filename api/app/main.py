"""FastAPI app (Lane C). Routes follow dev manual section 6.

    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import os
from typing import Any, List, Optional

import pymupdf
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from . import jobs
from .cad import cadquery_available

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "50"))

app = FastAPI(title="CAD to RFQ API", version="0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"], allow_headers=["*"],
)


def _get(job_id: str) -> dict:
    try:
        return jobs.load(job_id)
    except jobs.JobNotFound:
        raise HTTPException(404, "Job not found")


def _public(job: dict) -> dict:
    j = dict(job)
    j["views"] = [{"name": v["name"], "url": f"/jobs/{job['id']}/views/{v['name']}.png"} for v in job.get("views", [])]
    j["pdf_url"] = f"/jobs/{job['id']}/pdf" if job.get("pdf") else None
    j["unapproved"] = jobs.unapproved(job)
    j["working"] = job["status"] in jobs.WORKING
    return j


@app.get("/health")
def health():
    return {"ok": True, "draft_mode": jobs.draft_mode(), "cadquery": cadquery_available()}


@app.get("/jobs")
def list_jobs():
    return jobs.list_jobs()


@app.post("/jobs", status_code=201)
async def create_job(bg: BackgroundTasks, file: UploadFile = File(...)):
    name = file.filename or ""
    if not name.lower().endswith((".step", ".stp")):
        raise HTTPException(415, "Upload a STEP file (.step or .stp). DWG support is coming after the MVP.")
    data = await file.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File is over {MAX_UPLOAD_MB} MB. The MVP handles single parts, not large assemblies.")
    if not data:
        raise HTTPException(400, "The file is empty.")
    job = jobs.create(name, data)
    bg.add_task(jobs.run_extract, job["id"])
    return _public(job)


@app.post("/jobs/demo", status_code=201)
def create_demo(bg: BackgroundTasks):
    job = jobs.create_demo()
    bg.add_task(jobs.run_extract, job["id"])
    return _public(job)


@app.get("/demo/form")
def demo_form():
    return jobs.demo_form()


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    return _public(_get(job_id))


class CriticalDim(BaseModel):
    feature: str
    value: str
    unit: Optional[str] = "mm"


class Buyer(BaseModel):
    company: str
    contact: Optional[str] = ""
    email: Optional[str] = ""
    country: Optional[str] = "US"


class EngForm(BaseModel):
    part_name: str
    part_number: str
    revision: str = "A"
    material: str
    general_tolerance: str = "ISO 2768-m"
    critical_dims: List[CriticalDim] = []
    finish: Optional[str] = ""
    qty_breaks: List[int]
    target_delivery: str
    certs: List[str] = []
    packaging: Optional[str] = None
    buyer: Buyer
    quote_due: Optional[str] = None
    notes: Optional[str] = ""


@app.put("/jobs/{job_id}/form")
def save_form(job_id: str, form: EngForm, bg: BackgroundTasks):
    job = _get(job_id)
    if job["status"] in jobs.WORKING:
        raise HTTPException(409, f"Job is busy ({job['status']}). Try again in a moment.")
    if not job.get("cad_facts"):
        raise HTTPException(409, "CAD extraction has not finished for this job.")
    if not form.qty_breaks or any(q <= 0 for q in form.qty_breaks):
        raise HTTPException(422, "Enter at least one quantity above zero.")
    eng = {"schema_version": "1", **form.model_dump()}
    eng["critical_dims"] = [d for d in eng["critical_dims"] if d["feature"].strip() or d["value"].strip()]
    job = jobs.update(job_id, form=eng, status="drafting", pdf=None)
    bg.add_task(jobs.run_draft, job_id)
    return _public(job)


class FieldPatch(BaseModel):
    value: Any = None
    approved: Optional[bool] = None


@app.patch("/jobs/{job_id}/fields/{key}")
def patch_field(job_id: str, key: str, patch: FieldPatch):
    job = _get(job_id)
    if job["status"] not in ("review", "done"):
        raise HTTPException(409, "Fields can be edited once the draft is ready.")
    set_value = "value" in patch.model_fields_set
    return _public(jobs.edit_field(job_id, key, patch.value, patch.approved, set_value))


@app.post("/jobs/{job_id}/approve-all")
def approve_all(job_id: str):
    job = _get(job_id)
    for k in jobs.unapproved(job):
        job = jobs.edit_field(job_id, k, approved=True)
    return _public(job)


class RenderReq(BaseModel):
    supplier_copy: bool = False


@app.post("/jobs/{job_id}/render")
def render_pdf(job_id: str, bg: BackgroundTasks, req: RenderReq = RenderReq()):
    job = _get(job_id)
    if job["status"] not in ("review", "done"):
        raise HTTPException(409, "The draft has to be reviewed before export.")
    left = jobs.unapproved(job)
    if left:
        raise HTTPException(409, f"Approve or edit every AI field first: {', '.join(left)}.")
    job = jobs.update(job_id, status="rendering")
    bg.add_task(jobs.run_render, job_id, req.supplier_copy)
    return _public(job)


@app.get("/jobs/{job_id}/pdf")
def download_pdf(job_id: str):
    job = _get(job_id)
    if not job.get("pdf"):
        raise HTTPException(404, "No PDF yet. Export first.")
    path = os.path.join(jobs.job_dir(job_id), job["pdf"])
    return FileResponse(path, media_type="application/pdf", filename=job["pdf"])


@app.get("/jobs/{job_id}/views/{name}.png")
def view_png(job_id: str, name: str):
    job = _get(job_id)
    v = next((v for v in job.get("views", []) if v["name"] == name), None)
    if not v:
        raise HTTPException(404, "No such view")
    path = os.path.join(jobs.job_dir(job_id), v["key"])
    png = path[:-4] + ".png"
    if not os.path.isfile(png):
        doc = pymupdf.open(path)
        doc[0].get_pixmap(dpi=110, alpha=True).save(png)
        doc.close()
    return FileResponse(png, media_type="image/png")
