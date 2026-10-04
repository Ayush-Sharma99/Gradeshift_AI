"""GradeShift PrimePath UI Presenter & Runtime Context Package.

Pure-Python application service layer connecting the Streamlit product pages
(`app.py` and `pages/1..6`) to the verified `gradeshift` domain stack without
leaking Streamlit imports into domain modules.
"""
from __future__ import annotations

from .context import (
    ARTIFACTS_DIR,
    MODE_META,
    REPO_ROOT,
    ApprovalStatus,
    ExecutionMode,
    RuntimeContext,
    apply_fault_preset,
    load_runtime_context,
)
from .presenters import (
    ACTION_META,
    DEMO_STEP_KEYS,
    build_cockpit_view,
    build_demo_walkthrough,
    build_disposition_view,
    build_economic_view,
    build_executive_view,
    build_guardian_view,
    build_locked_validation_view,
    build_memory_assurance_view,
    build_quality_view,
    build_replay_view,
)

__all__ = [
    "ACTION_META",
    "ARTIFACTS_DIR",
    "ApprovalStatus",
    "DEMO_STEP_KEYS",
    "ExecutionMode",
    "MODE_META",
    "REPO_ROOT",
    "RuntimeContext",
    "apply_fault_preset",
    "build_cockpit_view",
    "build_demo_walkthrough",
    "build_disposition_view",
    "build_economic_view",
    "build_executive_view",
    "build_guardian_view",
    "build_locked_validation_view",
    "build_memory_assurance_view",
    "build_quality_view",
    "build_replay_view",
    "load_runtime_context",
]
