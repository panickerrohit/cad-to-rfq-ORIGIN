"""End-to-end API test in mock mode: upload STEP -> form -> review -> PDF.

Run from api/:  python -m pytest -q tests
"""
import os

import pytest

os.environ["DRAFT_MOCK"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

FX = os.path.join(os.path.dirname(__file__), "..", "fixtures")


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import jobs
    monkeypatch.setattr(jobs, "JOBS_DIR", str(tmp_path))
    from app.main import app
    return TestClient(app)


def test_full_flow(client):
    with open(os.path.join(FX, "step", "SB-1042_RevA.step"), "rb") as f:
        r = client.post("/jobs", files={"file": ("SB-1042_RevA.step", f, "application/octet-stream")})
    assert r.status_code == 201, r.text
    jid = r.json()["id"]
    job = client.get(f"/jobs/{jid}").json()  # background task ran inside the request in TestClient
    assert job["status"] == "awaiting_form", job["error"]
    assert job["fields"]["bbox_mm"]["source"] == "CAD"

    form = client.get("/demo/form").json()
    form.pop("schema_version")
    assert client.put(f"/jobs/{jid}/form", json=form).status_code == 200
    job = client.get(f"/jobs/{jid}").json()
    assert job["status"] == "review"
    assert job["unapproved"]  # AI fields start unapproved
    assert client.post(f"/jobs/{jid}/render").status_code == 409

    r = client.patch(f"/jobs/{jid}/fields/packaging", json={"value": "Bagged in 10s"})
    assert r.json()["fields"]["packaging"]["source"] == "ENG"
    client.post(f"/jobs/{jid}/approve-all")
    assert client.post(f"/jobs/{jid}/render", json={"supplier_copy": False}).status_code == 200
    job = client.get(f"/jobs/{jid}").json()
    assert job["status"] == "done", job["error"]
    pdf = client.get(job["pdf_url"])
    assert pdf.content[:4] == b"%PDF"


def test_rejects_non_step(client):
    r = client.post("/jobs", files={"file": ("x.dwg", b"AC1021", "application/octet-stream")})
    assert r.status_code == 415
