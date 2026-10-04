"""Dataset assembly for the quality estimator (Phase 5).

Builds (features @ t  ->  future-lab truth) rows from SIMULATED episodes, with
strict separation between:
  * FEATURES: as-of-safe vector at decision time t (never sees past t);
  * TARGET:   the next lab result for the associated material window, which is
              legitimately FUTURE truth used only for supervision/evaluation.

Target definition
  variable ............ MFI of the material window associated with t (g/10min)
  prediction ts ....... decision time t
  association rule .... earliest lab with collected_at in [t, t+horizon]
                        (that lab samples the material being produced around t)
  supervision ......... LabSample.mfi (SIMULATED, with lab noise)
  tolerance ........... horizon = Policy.decision_horizon_min (default 240 min)
  multiple labs ....... earliest-collected qualifying sample is used
  no valid truth ...... row carries target=None and is excluded from fit/metrics
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

import numpy as np

from . import config as C
from . import simulate as S
from .events import compute_boundaries
from .features import FEATURE_NAMES, build_features
from .material_identity import MaterialMapParams
from .schemas import TransitionEvent

DATASET_VERSION = "ds-v1"
_CORPUS_BASE = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class DatasetRow:
    event_id: str
    decision_time: datetime
    features: dict[str, float]
    target_mfi: Optional[float]
    target_sample_id: Optional[str]
    phase: str
    direction: str
    online_at_t: float               # process value at t (for lineage display)

    @property
    def has_target(self) -> bool:
        return self.target_mfi is not None


def _target_for(event: TransitionEvent, t: datetime, horizon_min: float
                ) -> tuple[Optional[float], Optional[str]]:
    """Earliest lab collected in [t, t+horizon]; its MFI is the supervision truth."""
    hi = t + timedelta(minutes=horizon_min)
    cand = sorted((s for s in event.labs if t <= s.collected_at <= hi),
                  key=lambda s: s.collected_at)
    if not cand:
        return None, None
    return float(cand[0].mfi), cand[0].sample_id


def build_rows(event: TransitionEvent, *,
               horizon_min: float = C.POLICY.decision_horizon_min,
               step_min: float = 20.0, warmup_min: float = 30.0,
               map_params: Optional[MaterialMapParams] = None) -> list[DatasetRow]:
    """Sample decision times across one episode and assemble causal rows."""
    b = compute_boundaries(event)
    end = event.ended_at or (max((r.end for r in event.routing), default=event.started_at))
    rows: list[DatasetRow] = []
    offset = warmup_min
    total = (end - event.started_at).total_seconds() / 60.0
    while offset <= total:
        t = event.started_at + timedelta(minutes=offset)
        feats = build_features(event, t, map_params)
        tgt, sid = _target_for(event, t, horizon_min)
        rows.append(DatasetRow(
            event_id=event.event_id, decision_time=t, features=feats,
            target_mfi=tgt, target_sample_id=sid, phase=b.phase_at(t),
            direction=event.direction, online_at_t=feats.get("MFI_online_last", float("nan"))))
        offset += step_min
    return rows


def make_corpus(directions: Sequence[tuple[str, str]], n_per_dir: int = 3,
                params: Optional[S.EpisodeParams] = None,
                spacing_min: float = 2000.0) -> list[TransitionEvent]:
    """A reproducible set of SIMULATED episodes with STAGGERED start times (so the
    event-level chronological split is well defined). Deterministic in seeds."""
    p = params or S.EpisodeParams()
    events: list[TransitionEvent] = []
    i = 0
    for (gf, gt) in directions:
        for j in range(n_per_dir):
            start = _CORPUS_BASE + timedelta(minutes=spacing_min * i)
            eid = f"EP-{gf}{gt}-{j:02d}"
            events.append(S.generate_episode(eid, gf, gt, seed=1000 + i,
                                             start_time=start, params=p))
            i += 1
    return events


def rows_to_xy(rows: Sequence[DatasetRow], labeled_only: bool = True
               ) -> tuple[np.ndarray, np.ndarray, list[DatasetRow]]:
    """Vectorize rows into (X, y, kept_rows) in canonical FEATURE_NAMES order."""
    kept = [r for r in rows if (r.has_target or not labeled_only)]
    X = np.array([[r.features[n] for n in FEATURE_NAMES] for r in kept], dtype=float)
    y = np.array([r.target_mfi if r.target_mfi is not None else np.nan for r in kept],
                 dtype=float)
    if X.size == 0:
        X = X.reshape(0, len(FEATURE_NAMES))
    return X, y, kept
