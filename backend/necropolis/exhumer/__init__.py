"""The exhumer: a domain's endpoint history from the Internet Archive alone (spec: .kiro/specs/exhumer).

Passive (safety.md rule 1): every request goes to web.archive.org through `necropolis.archive.ArchiveClient`. Never
import netguard, ownership or prober from here (structure.md).
"""

from __future__ import annotations

from necropolis.exhumer.aggregate import FALLBACK_WINDOW, aggregate, current_frontend
from necropolis.exhumer.captures import CDX_CAP, cdx_captures, to_capture
from necropolis.exhumer.miner import mine_js
from necropolis.exhumer.models import (
    Capture,
    EndpointRecord,
    ExhumeResult,
    FrontendRef,
    InvalidTarget,
    ScriptCapture,
    ScriptStats,
    Target,
)
from necropolis.exhumer.run import ExhumeJob, run_exhume
from necropolis.exhumer.scripts import SCRIPT_LIMIT, ScriptCandidate, candidates_from, pick_scripts, script_srcs
from necropolis.exhumer.target import validate_target

__all__ = [
    "CDX_CAP",
    "FALLBACK_WINDOW",
    "SCRIPT_LIMIT",
    "Capture",
    "EndpointRecord",
    "ExhumeJob",
    "ExhumeResult",
    "FrontendRef",
    "InvalidTarget",
    "ScriptCandidate",
    "ScriptCapture",
    "ScriptStats",
    "Target",
    "aggregate",
    "candidates_from",
    "cdx_captures",
    "current_frontend",
    "mine_js",
    "pick_scripts",
    "run_exhume",
    "script_srcs",
    "to_capture",
    "validate_target",
]
