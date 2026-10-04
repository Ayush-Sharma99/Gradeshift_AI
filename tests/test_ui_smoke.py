"""Headless Streamlit AppTest Smoke Suite for GradeShift PrimePath.

Executes `app.py` (PrimePath Decision Cockpit) and all 6 product pages
(`pages/1..6`) via `streamlit.testing.v1.AppTest` and asserts zero uncaught
exceptions on every screen.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parent.parent

UI_PAGES = [
    "app.py",
    "pages/1_Grade_Transition.py",
    "pages/2_Soft_Sensor.py",
    "pages/3_AI_Optimizer.py",
    "pages/4_Safety.py",
    "pages/5_Economics.py",
    "pages/6_Digital_Twin.py",
]


@pytest.mark.parametrize("page_rel_path", UI_PAGES)
def test_streamlit_page_renders_without_exception(page_rel_path: str):
    page_path = REPO_ROOT / page_rel_path
    assert page_path.exists(), f"Missing UI page: {page_path}"
    at = AppTest.from_file(str(page_path), default_timeout=60)
    at.run(timeout=60)
    assert len(at.exception) == 0, (
        f"Streamlit page {page_rel_path} raised exception(s): "
        f"{[e.value for e in at.exception]}"
    )
    assert len(at.markdown) > 0
