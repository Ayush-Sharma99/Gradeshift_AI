"""Architecture guard — domain packages must never import streamlit (ui → domain,
never the reverse). Enforces the dependency direction from the implementation plan."""
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "gradeshift"


def test_domain_never_imports_streamlit():
    offenders = []
    for py in SRC.rglob("*.py"):
        if "ui" in py.relative_to(SRC).parts:
            continue  # the ui/ presenter layer is the only place streamlit is allowed
        text = py.read_text(encoding="utf-8")
        if "import streamlit" in text:
            offenders.append(str(py.relative_to(SRC)))
    assert not offenders, f"domain modules import streamlit: {offenders}"
