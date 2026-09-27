"""Smoke tests for Lane B. Run from api/:  python -m pytest -q tests"""
import json
import os
from types import SimpleNamespace

from app.ai import draft
from app.ai.draft import DraftOut
from app.cli import merge
from app.pdf import render

FX = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def load(name):
    with open(os.path.join(FX, name)) as f:
        return json.load(f)


def test_mock_draft_matches_contract():
    d = draft(load("cad_facts.json"), load("eng_form.json"), mock=True)
    assert d["schema_version"] == "1"
    assert set(d["fields"]) == {"scope_of_work", "process_notes", "inspection_requirements", "packaging", "quote_form_questions"}
    assert any(f["field"] == "packaging" for f in d["flags"])


def test_conflict_is_flagged():
    d = draft(load("cad_facts.json"), load("eng_form_conflict.json"), mock=True)
    assert any(f["severity"] == "error" and f["field"] == "finish" for f in d["flags"])


def test_fixture_draft_is_valid():
    DraftOut.model_validate(load("draft.json"))


def test_claude_path_with_fake_client():
    parsed = DraftOut.model_validate(load("draft.json"))
    calls = []

    class Msgs:
        def parse(self, **kw):
            calls.append(kw)
            return SimpleNamespace(stop_reason="end_turn", parsed_output=parsed)

    d = draft(load("cad_facts.json"), load("eng_form.json"), mock=False, client=SimpleNamespace(messages=Msgs()))
    assert d["fields"]["packaging"]["value"] == "Individually bagged, bulk boxed"
    assert calls[0]["output_format"] is DraftOut
    assert "views" not in json.loads(calls[0]["messages"][0]["content"])["cad"]


def test_render_fixture_and_edge_cases():
    fields = load("fields.json")
    pdf = render(fields, views_root=os.path.join(FX, ".."))
    assert pdf[:4] == b"%PDF"
    # empty job, A4, supplier copy, awkward characters: must still render
    odd = {"fields": {"part_name": {"value": "Bracket <v2> & co", "source": "ENG"}},
           "options": {"page_size": "a4", "include_internal_page": False, "show_tags": False}}
    assert render(odd)[:4] == b"%PDF"


def test_merge_eng_beats_ai():
    eng = load("eng_form.json"); eng["packaging"] = "Foam tray"
    f = merge(load("cad_facts.json"), eng, load("draft.json"))
    assert f["fields"]["packaging"] == {"value": "Foam tray", "source": "ENG", "approved": True}
