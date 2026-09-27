"""Rule-based stand-in for the Claude call. Same output shape as draft().

Used when there is no API key (DRAFT_MOCK=1 / --mock) and as the demo fallback.
It only rephrases what is in the inputs and runs a few simple conflict checks.
"""
from __future__ import annotations


def _has(s, *words):
    s = (s or "").lower()
    return any(w in s for w in words)


def mock_draft(cad: dict, eng: dict) -> dict:
    material = eng.get("material") or ""
    finish = eng.get("finish") or ""
    certs = eng.get("certs") or []
    qtys = eng.get("qty_breaks") or []
    crit = eng.get("critical_dims") or []
    flags = []

    scope = ("Supply finished, inspected parts per the enclosed specification sheet and 3D model"
             + (f", in {material}" if material else "")
             + (f", finished {finish}" if finish else "") + ". "
             + (f"Quote each quantity break ({', '.join(str(q) for q in qtys)}) separately. " if qtys else "")
             + "Show any one-time tooling, fixturing or programming (NRE) on its own line.")

    if _has(material, "alum", "6061", "7075", "5052"):
        proc = "Likely CNC milling from plate or bar. Supplier to confirm routing and number of setups."
    elif _has(material, "steel", "stainless"):
        proc = "Likely CNC machining or laser cut and form, depending on geometry. Supplier to propose routing."
    else:
        proc = "Supplier to propose the manufacturing route."
    if finish:
        proc += f" Finish after all machining: {finish}."

    insp = []
    if crit:
        insp.append("Inspect critical dimensions: " + "; ".join(
            f"{c.get('feature')} {c.get('value')} {c.get('unit') or ''}".strip() for c in crit) + ".")
    if certs:
        insp.append("Ship with: " + ", ".join(certs) + ".")
    if not insp:
        insp.append("Supplier to state standard inspection and documentation.")

    if eng.get("packaging"):
        pack = {"value": eng["packaging"], "confidence": 1.0, "note": "From engineer input"}
    else:
        pack = {"value": "Individually bagged or separated so finished faces do not touch; boxes labelled with "
                         "part number, revision, quantity and PO.", "confidence": 0.6,
                "note": "Not specified; default proposed"}
        flags.append({"severity": "warn", "field": "packaging", "message": "Packaging not specified; proposed a default."})

    if _has(finish, "anodiz") and material and not _has(material, "alum", "6061", "7075", "5052", "titan"):
        flags.append({"severity": "error", "field": "finish",
                      "message": f"Anodize is specified but material is {material}. Anodizing applies to aluminum/titanium."})
    if not material:
        flags.append({"severity": "error", "field": "material", "message": "Material is missing."})
    if not finish:
        flags.append({"severity": "warn", "field": "finish", "message": "Finish not specified; suppliers will assume as-machined."})
    if (cad.get("solid_count") or 1) > 1:
        flags.append({"severity": "error", "field": "solid_count", "message": "STEP file has more than one solid."})
    for w in cad.get("warnings") or []:
        if _has(w, "no pmi"):
            flags.append({"severity": "info", "field": "cad", "message": "STEP has no PMI; tolerances come only from the form."})
    if eng.get("quote_due") and eng.get("target_delivery") and eng["quote_due"] >= eng["target_delivery"]:
        flags.append({"severity": "error", "field": "quote_due", "message": "Quote due date is on or after target delivery."})

    questions = ["Unit price and lead time per quantity break", "NRE (programming, fixtures, gauges)"]
    if finish:
        questions.append("Is finishing done in house or by a sub-tier supplier?")
    questions.append("Any DFM suggestions that reduce cost?")

    return {
        "fields": {
            "scope_of_work": {"value": scope, "confidence": 0.85, "note": "From material, finish, quantities (mock)"},
            "process_notes": {"value": proc, "confidence": 0.6, "note": "Inferred from material (mock)"},
            "inspection_requirements": {"value": " ".join(insp), "confidence": 0.8, "note": "From critical dims and certs (mock)"},
            "packaging": pack,
            "quote_form_questions": {"value": questions, "confidence": 0.9, "note": ""},
        },
        "flags": flags,
    }
