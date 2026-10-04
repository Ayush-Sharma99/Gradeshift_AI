# Historical Archive — GradeShift Ideation & Forensic Audit Materials

> **HISTORICAL ONLY — NOT THE CURRENT PRODUCT CONTRACT.**  
> Do **not** treat the controller-first / offline-RL / NMPC-CBF architecture described in these historical files as the current GradeShift PrimePath product specification.  
> The authoritative current product contract is [`GradeShift_Product_Freeze_Engineering_Handoff.md`](../GradeShift_Product_Freeze_Engineering_Handoff.md), [`AGENTS.md`](../AGENTS.md), and [`PROJECT_HANDOFF.md`](../PROJECT_HANDOFF.md).

---

## Inventory of Preserved Historical Materials

| File | Origin | Role & Historical Context |
|---|---|---|
| [`RGIPT_Ayush-Sharma_Idea01.pdf`](RGIPT_Ayush-Sharma_Idea01.pdf) *(also at repo root)* | Initial HMEL i-QUEST 2026 Round-1 Submission | Original 14-slide ideation deck proposing a 3-tier controller stack (MoM + LSTM + EKF soft sensor, offline CQL RL optimizer, NMPC/CBF safety shield). Preserved for audit traceability and claim reconciliation in [`docs/CLAIMS.md`](../docs/CLAIMS.md). |
| [`PROJECT_STATUS_AUDIT.md`](PROJECT_STATUS_AUDIT.md) *(also at repo root)* | Pre-PrimePath Forensic Audit (2026-10-01) | Forensic audit of the initial commit `5da04be` identifying the "Two Projects" gap and defects `D1–D7` (including the uncalibrated quadratic MFI polynomial in `reactor_simulator.py`). |
| [`CLAUDE_CODE_MASTER_PROMPT.md`](CLAUDE_CODE_MASTER_PROMPT.md) *(also at repo root)* | Deprecated Controller-First Prompt | Historical prompt written before the PrimePath product freeze (`GradeShift_Product_Freeze_Engineering_Handoff.md`). **Superseded by `AGENTS.md` and `PROJECT_HANDOFF.md`.** |
| [`legacy_prototype/`](legacy_prototype/) | Initial Prototype Snapshot (`5da04be`) | Archived copies of `reactor_simulator.py`, `soft_sensor.py`, and `transition_optimizer.py` as inherited prior to the PrimePath domain rewrite (`src/gradeshift/`). |
