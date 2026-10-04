# Experiments — Non-Core Research & Counterfactual Modules

> **NON-CORE EXPERIMENTAL DIRECTORY.**  
> Files in `experiments/` are isolated from the authoritative GradeShift PrimePath decision stack (`src/gradeshift/`).  
> PrimePath is a read-only, human-authorized commercial-disposition decision layer (`HOLD`, `SAMPLE_NOW`, `PRIME_RELEASE_CANDIDATE`, `ABSTAIN`) and does **not** manipulate reactor setpoints or use reinforcement learning in its core engine.

---

## Contents

- [`legacy_control_counterfactual.py`](legacy_control_counterfactual.py): Archived open-loop scalar switch-time search (`scipy.optimize.minimize_scalar`, formerly `transition_optimizer.py`). Preserved strictly as a historical/experimental counterfactual reference with all inaccurate "Reinforcement Learning / CQL" labels removed.
