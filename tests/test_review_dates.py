"""Every hand-set parameter file carries a review_by date, and the suite fails once one is overdue (staleness control)."""
import json
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "indiafacts" / "data"
NOT_PARAMETERS = {"companies.json", "security_master.json"}      # data lists, checked by their own tests


def test_every_parameter_file_has_a_review_date_that_is_not_overdue():
    seen = 0
    for p in sorted(DATA.glob("*.json")):
        if p.name in NOT_PARAMETERS:
            continue
        d = json.loads(p.read_text())
        assert isinstance(d, dict) and d.get("review_by"), f"{p.name} has no review_by date"
        assert date.fromisoformat(d["review_by"]) >= date.today(), f"{p.name} is overdue for review (review_by {d['review_by']})"
        seen += 1
    assert seen >= 10
