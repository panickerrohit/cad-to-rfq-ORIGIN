"""CAD extraction (Lane A): STEP file -> cad_facts dict + 2D view PDFs.

extract(path, out_dir=None) -> dict matching fixtures/cad_facts.json:

    {"schema_version": "1", "source": {...}, "bbox_mm": {"x","y","z"}, "volume_mm3",
     "surface_area_mm2", "solid_count", "is_assembly", "views": [{"name","key"}], "warnings": [...]}

With CadQuery installed this is the real thing (dev manual 5.1): bbox, volume,
area, solid count, units sanity check, and front/top/right/iso views exported
as SVG and converted to vector PDF with pymupdf.

Without CadQuery (it is a heavy install) a text fallback reads the STEP file
directly: units from the header and a bounding box from CARTESIAN_POINT
entities. Volume, area and views are left empty and a warning says why, so the
rest of the pipeline still runs.
"""
from __future__ import annotations

import os
import re

VIEWS = {  # name -> projection direction
    "front": (0, -1, 0),
    "top": (0, 0, 1),
    "right": (1, 0, 0),
    "iso": (1, -1, 1),
}


class CadError(RuntimeError):
    """A file we can't or won't process (bad STEP, assembly). Message is shown to the user."""


def cadquery_available() -> bool:
    try:
        import cadquery  # noqa: F401
        return True
    except Exception:
        return False


def extract(path: str, out_dir: str | None = None) -> dict:
    out_dir = out_dir or os.path.join(os.path.dirname(os.path.abspath(path)), "views")
    os.makedirs(out_dir, exist_ok=True)
    head = _read_head(path)
    if "ISO-10303-21" not in head:
        raise CadError("This doesn't look like a STEP file (missing ISO-10303-21 header).")
    facts = {
        "schema_version": "1",
        "source": {"filename": os.path.basename(path), "type": "step", "units": "mm"},
        "bbox_mm": None, "volume_mm3": None, "surface_area_mm2": None,
        "solid_count": None, "is_assembly": False, "views": [], "warnings": [],
    }
    file_units = _units_from_text(head)
    if file_units != "mm":
        facts["warnings"].append(f"STEP file units are {file_units}; values converted to mm.")
    if not any(k in head.upper() for k in ("DIMENSIONAL_SIZE", "DRAUGHTING_CALLOUT", "GEOMETRIC_TOLERANCE")):
        facts["warnings"].append("No PMI found in STEP")

    if cadquery_available():
        _extract_cadquery(path, out_dir, facts)
    else:
        _extract_text(path, facts, file_units)

    bb = facts["bbox_mm"]
    if bb:
        big, small = max(bb.values()), min(v for v in bb.values() if v > 0) if any(bb.values()) else 0
        if big > 20000:
            facts["warnings"].append(f"Part is {big:.0f} mm long; check the STEP file units.")
        elif 0 < big < 0.5:
            facts["warnings"].append(f"Part is only {big:.3f} mm long; check the STEP file units.")
        elif small or big:
            facts["warnings"].append("Units look plausible")
    return facts


# ------------------------------------------------------------------ CadQuery path
def _extract_cadquery(path, out_dir, facts):
    import cadquery as cq
    import pymupdf

    try:
        shape = cq.importers.importStep(path)
    except Exception as e:  # OCP raises a zoo of types
        raise CadError(f"Could not read the STEP file: {e}") from e
    solids = shape.solids().vals()
    if not solids:
        raise CadError("The STEP file contains no solid bodies.")
    facts["solid_count"] = len(solids)
    if len(solids) > 1:
        facts["is_assembly"] = True
        raise CadError(f"The file has {len(solids)} solids. The MVP handles one single part per RFQ; "
                       "export the part on its own and upload again.")
    solid = solids[0]
    bb = solid.BoundingBox()
    facts["bbox_mm"] = {"x": round(bb.xlen, 2), "y": round(bb.ylen, 2), "z": round(bb.zlen, 2)}
    facts["volume_mm3"] = round(solid.Volume(), 1)
    facts["surface_area_mm2"] = round(solid.Area(), 1)

    for name, direction in VIEWS.items():
        svg = os.path.join(out_dir, f"{name}.svg")
        pdf = os.path.join(out_dir, f"{name}.pdf")
        try:
            cq.exporters.export(shape, svg, exportType="SVG", opt={
                "width": 400, "height": 300, "marginLeft": 20, "marginTop": 20,
                "projectionDir": direction, "showAxes": False, "showHidden": name != "iso",
                "strokeWidth": 0.6, "strokeColor": (27, 36, 48), "hiddenColor": (150, 160, 175),
            })
            with open(svg, "rb") as f:
                doc = pymupdf.open(stream=f.read(), filetype="svg")
            with open(pdf, "wb") as f:
                f.write(doc.convert_to_pdf())
            doc.close()
            facts["views"].append({"name": name, "key": pdf})
        except Exception as e:
            facts["warnings"].append(f"Could not render the {name} view: {e}")


# ------------------------------------------------------------------ text fallback
_POINT = re.compile(r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*([-+0-9.EeDd]+)\s*,\s*([-+0-9.EeDd]+)\s*,\s*([-+0-9.EeDd]+)\s*\)")
_SOLID = re.compile(r"MANIFOLD_SOLID_BREP|BREP_WITH_VOIDS")


def _read_head(path, n=400_000):
    with open(path, "r", encoding="latin-1", errors="replace") as f:
        return f.read(n)


def _units_from_text(text):
    t = text.upper().replace(" ", "")
    if "'INCH'" in t:
        return "inch"
    if "SI_UNIT(.MILLI.,.METRE.)" in t:
        return "mm"
    if "SI_UNIT(.CENTI.,.METRE.)" in t:
        return "cm"
    if "SI_UNIT($,.METRE.)" in t:
        return "m"
    return "mm"


def _extract_text(path, facts, units):
    with open(path, "r", encoding="latin-1", errors="replace") as f:
        text = f.read()
    scale = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "inch": 25.4}[units]
    xs, ys, zs = [], [], []
    for m in _POINT.finditer(text):
        try:
            x, y, z = (float(v.replace("D", "E").replace("d", "e")) * scale for v in m.groups())
        except ValueError:
            continue
        xs.append(x); ys.append(y); zs.append(z)
    solids = len(_SOLID.findall(text))
    facts["solid_count"] = solids or None
    if solids > 1:
        facts["is_assembly"] = True
        raise CadError(f"The file has {solids} solids. The MVP handles one single part per RFQ; "
                       "export the part on its own and upload again.")
    if not xs:
        raise CadError("No geometry found in the STEP file.")
    facts["bbox_mm"] = {"x": round(max(xs) - min(xs), 2), "y": round(max(ys) - min(ys), 2),
                        "z": round(max(zs) - min(zs), 2)}
    facts["warnings"].append("CadQuery is not installed on the server: bounding box estimated from STEP "
                             "points (may include construction points); volume, area and views unavailable.")
