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


def test_deployment_artifacts_and_cross_version_pickle_shims(monkeypatch):
    """Deployment Smoke Matrix Tests 1–4 + Python 3.14 / sklearn >=1.7 `_loss` shim."""
    import sys
    from gradeshift.applicability import ApplicabilityDetector
    from gradeshift.calibrator import SplitConformalCalibrator
    from gradeshift.estimator import GBMQualityEstimator, ensure_pickle_compat_shims
    from gradeshift.ui.context import load_runtime_context

    gbm_path = REPO_ROOT / "artifacts" / "phase5" / "gbm_mfi.joblib"
    cal_path = REPO_ROOT / "artifacts" / "phase6" / "calibrator_gbm.joblib"
    det_path = REPO_ROOT / "artifacts" / "phase7" / "applicability_detector.joblib"

    # Simulate Python 3.14 / scikit-learn >= 1.7 where top-level `_loss` is absent from sys.modules
    monkeypatch.delitem(sys.modules, "_loss", raising=False)
    assert "_loss" not in sys.modules

    # Test 2: GBMQualityEstimator.load registers `_loss` shim and loads cleanly
    gbm = GBMQualityEstimator.load(str(gbm_path))
    assert "_loss" in sys.modules
    assert gbm.model_version == "gbm-mfi-v1"
    assert len(gbm.feature_names) == 41


    # Test 3: SplitConformalCalibrator.load
    cal = SplitConformalCalibrator.load(str(cal_path))
    assert cal.estimator_version == "gbm-mfi-v1"
    assert cal.nominal_coverage == 0.90

    # Test 4: ApplicabilityDetector.load
    det = ApplicabilityDetector.load(str(det_path))
    assert det.detector_version == "iforest-knn-v1"
    assert set(det.known_directions) == {"A->B", "A->C", "B->A", "C->A"}


    # Test 1: Full RuntimeContext load with force_reload=True
    ensure_pickle_compat_shims()
    rt = load_runtime_context(force_reload=True)
    assert rt.gbm.model_version == "gbm-mfi-v1"
    assert len(rt.corpus) == 18


def test_deployment_runtime_pinning_files():
    """Verify .python-version, runtime.txt, and requirements.txt are present and clean."""
    py_ver = (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    rt_txt = (REPO_ROOT / "runtime.txt").read_text(encoding="utf-8").strip()
    reqs = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert py_ver.startswith("3.10")
    assert rt_txt.startswith("python-3.10")
    assert "torch" not in reqs
    assert "scikit-learn==1.6.1" in reqs
    assert "numpy==1.26.4" in reqs


