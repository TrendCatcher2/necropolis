"""Regression corpus (endpoint-normaliser task 5.3): raw input -> expected output, one JSON object per line.

Add a line whenever a bug is found. Sources: the demo site's own URLs and JS, and hand-written example.com cases
(testing.md). Recorded CDX rows join it when exhumer task 1.3 records them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from necropolis.normaliser import Normalised, Rejected, normalise

CORPUS = Path(__file__).parent.parent / "fixtures" / "normaliser_corpus.jsonl"
ROWS: list[dict[str, Any]] = [json.loads(line) for line in CORPUS.read_text(encoding="utf-8").splitlines() if line]


@pytest.mark.parametrize("row", ROWS, ids=[row["raw"][:60] for row in ROWS])
def test_corpus(row: dict[str, Any]) -> None:
    result = normalise(row["raw"], base_host=row["base_host"], mimetype=row["mimetype"])
    if "rejected" in row["expect"]:
        assert result == Rejected(reason=row["expect"]["rejected"])
    else:
        assert isinstance(result, Normalised), result
        assert result.model_dump(mode="json") == row["expect"]


def test_corpus_has_the_demo_zombie() -> None:
    """The archived v1 user captures and the v1 JS path are one tombstone, apart from v2's."""
    keys = {
        json.dumps(row["expect"]["key"], sort_keys=True)
        for row in ROWS
        if "users" in row["raw"] and "key" in row["expect"] and "onrender" in row["expect"]["key"]["host"]
    }
    assert len(keys) == 2  # /api/v1/users/{id} and /api/v2/users/{id}
