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


def test_cockpit_interactive_stepper_and_mode_transitions():
    """Phase 25 #15: Verify interactive stepper buttons and mode switching in app.py."""
    at = AppTest.from_file(str(REPO_ROOT / "app.py"), default_timeout=60)
    at.run(timeout=60)
    assert len(at.exception) == 0

    # Click Demo Stepper buttons (T1_HOLD -> T2_SAMPLE_NOW -> T6_FAULT_ABSTAIN -> T3_PRIME_CANDIDATE)
    for btn_key in ("btn_T1_HOLD", "btn_T2_SAMPLE_NOW", "btn_T6_FAULT_ABSTAIN", "btn_T3_PRIME_CANDIDATE"):
        at.button(key=btn_key).click().run(timeout=60)
        assert len(at.exception) == 0

    # Switch Operating Mode to LOCKED_VALIDATION and SYNTHETIC_REPLAY
    at.sidebar.selectbox[0].select("LOCKED_VALIDATION").run(timeout=60)
    assert len(at.exception) == 0
    at.sidebar.selectbox[0].select("SYNTHETIC_REPLAY").run(timeout=60)
    assert len(at.exception) == 0

