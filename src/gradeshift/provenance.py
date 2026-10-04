"""Provenance labelling. Every observation and economic input carries one of these.

Never allow SIMULATED data to be presented as MEASURED HMEL data.
"""
from __future__ import annotations

from enum import Enum


class Provenance(str, Enum):
    """Source/evidence label propagated to every output."""

    MEASURED = "MEASURED"                     # real instrument/lab measurement
    PUBLICLY_VERIFIED = "PUBLICLY_VERIFIED"   # published, citable
    INDUSTRY_BENCHMARK = "INDUSTRY_BENCHMARK" # typical industry value
    ASSUMPTION = "ASSUMPTION"                 # declared assumption
    SIMULATED = "SIMULATED"                   # produced by the seeded generator
    ILLUSTRATIVE = "ILLUSTRATIVE"             # for display only, not evidence

    @property
    def is_evidence(self) -> bool:
        """True for provenances that may back a quantitative claim."""
        return self in (
            Provenance.MEASURED,
            Provenance.PUBLICLY_VERIFIED,
            Provenance.INDUSTRY_BENCHMARK,
        )


class EvidenceLevel(str, Enum):
    """Claim evidence ladder. The competition POC may claim at most E3."""

    E0 = "E0"  # assumption
    E1 = "E1"  # theoretical
    E2 = "E2"  # simulation
    E3 = "E3"  # controlled prototype
    E4 = "E4"  # historical / public-data validation
    E5 = "E5"  # industrial validation


POC_MAX_EVIDENCE = EvidenceLevel.E3
