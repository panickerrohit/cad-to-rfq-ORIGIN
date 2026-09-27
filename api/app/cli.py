"""Command line for Lane B, and the demo fallback.

    python -m app.cli draft  fixtures/cad_facts.json fixtures/eng_form.json -o out/draft.json [--mock]
    python -m app.cli merge  fixtures/cad_facts.json fixtures/eng_form.json out/draft.json -o out/fields.json
    python -m app.cli render out/fields.json -o out/rfq.pdf [--views-root .]
    python -m app.cli run    fixtures/cad_facts.json fixtures/eng_form.json -o out/ [--mock]
    python -m app.cli run    demo.step form.json -o out/          # uses app.cad.extract once Person 1's code is in

`merge` is a simple stand-in for Person 3's review step: CAD and ENG win over AI,
everything is marked approved. The web app replaces it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

from .ai import draft, DraftError
from .pdf import render

CAD_KEYS = {"bbox_mm", "volume_mm3", "surface_area_mm2", "solid_count"}
ENG_KEYS = ["part_name", "part_number", "revision", "material", "general_tolerance", "critical_dims", "finish",
            "qty_breaks", "target_delivery", "certs", "packaging", "buyer", "quote_due", "notes"]


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(obj, p):
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def merge(cad: dict, eng: dict, drf: dict, job_id: str | None = None) -> dict:
    fields = {}
    for k, e in drf.get("fields", {}).items():
        fields[k] = {"value": e["value"], "source": "AI", "approved": True, "note": e.get("note", "")}
    for k in CAD_KEYS:
        if cad.get(k) is not None:
            fields[k] = {"value": cad[k], "source": "CAD", "approved": True}
    if (cad.get("source") or {}).get("filename"):
        fields["source_filename"] = {"value": cad["source"]["filename"], "source": "CAD", "approved": True}
    for k in ENG_KEYS:
        if eng.get(k) not in (None, "", []):
            fields[k] = {"value": eng[k], "source": "ENG", "approved": True}  # ENG beats AI (e.g. packaging)
    return {"schema_version": "1", "job_id": job_id or str(uuid.uuid4()), "fields": fields,
            "flags": drf.get("flags", []), "views": cad.get("views", []),
            "options": {"page_size": "letter", "include_internal_page": True, "show_tags": True}}


def _cad_facts(path):
    if path.lower().endswith((".step", ".stp")):
        try:
            from .cad import extract  # Person 1's lane
        except ImportError:
            sys.exit("app.cad.extract not found. Pass a cad_facts.json instead of a STEP file.")
        facts = extract(path)
        return facts.model_dump() if hasattr(facts, "model_dump") else facts
    return load(path)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sp = ap.add_subparsers(dest="cmd", required=True)
    d = sp.add_parser("draft"); d.add_argument("cad"); d.add_argument("eng"); d.add_argument("-o", "--out", default="out/draft.json")
    d.add_argument("--mock", action="store_true"); d.add_argument("--model")
    m = sp.add_parser("merge"); m.add_argument("cad"); m.add_argument("eng"); m.add_argument("draft")
    m.add_argument("-o", "--out", default="out/fields.json")
    r = sp.add_parser("render"); r.add_argument("fields"); r.add_argument("-o", "--out", default="out/rfq.pdf")
    r.add_argument("--views-root", default=".")
    u = sp.add_parser("run"); u.add_argument("cad", help="cad_facts.json or a .step file"); u.add_argument("eng")
    u.add_argument("-o", "--out", default="out"); u.add_argument("--mock", action="store_true"); u.add_argument("--model")
    u.add_argument("--views-root", default=".")
    a = ap.parse_args(argv)

    try:
        if a.cmd == "draft":
            save(draft(load(a.cad), load(a.eng), mock=a.mock or None, model=a.model), a.out)
        elif a.cmd == "merge":
            save(merge(load(a.cad), load(a.eng), load(a.draft)), a.out)
        elif a.cmd == "render":
            with open(a.out, "wb") as f:
                f.write(render(load(a.fields), views_root=a.views_root))
        elif a.cmd == "run":
            cad, eng = _cad_facts(a.cad), load(a.eng)
            drf = draft(cad, eng, mock=a.mock or None, model=a.model)
            fields = merge(cad, eng, drf)
            save(cad, os.path.join(a.out, "cad_facts.json"))
            save(drf, os.path.join(a.out, "draft.json"))
            save(fields, os.path.join(a.out, "fields.json"))
            pn = fields["fields"].get("part_number", {}).get("value", "part")
            pdf = os.path.join(a.out, f"RFQ_{pn}.pdf")
            with open(pdf, "wb") as f:
                f.write(render(fields, views_root=a.views_root))
            for fl in drf.get("flags", []):
                print(f"[{fl['severity'].upper()}] {fl['field']}: {fl['message']}")
            a.out = pdf
    except DraftError as e:
        sys.exit(f"Draft failed: {e}")
    print(a.out)


if __name__ == "__main__":
    main()
