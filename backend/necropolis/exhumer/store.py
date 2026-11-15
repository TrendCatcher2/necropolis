"""Saving an exhume run (exhumer design, SQLite tables). No query value and no response body is written."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime

from necropolis.exhumer.models import ExhumeResult, FrontendRef, Target
from necropolis.normaliser import EndpointKey


def key_json(key: EndpointKey) -> str:
    return json.dumps(key.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def save_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    target: Target,
    years: tuple[int, int] | None,
    result: ExhumeResult,
    refs: Iterable[FrontendRef],
    started_at: datetime,
    finished_at: datetime,
) -> None:
    with conn:
        conn.execute(
            "INSERT INTO exhume_runs (id, host, scope, year_from, year_to, status, failed_phase, capped, dating,"
            " rejected, scripts, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                target.host,
                target.scope,
                years[0] if years else None,
                years[1] if years else None,
                result.status,
                result.failed_phase,
                int(result.capped),
                result.dating,
                json.dumps(result.rejected, sort_keys=True),
                result.scripts.model_dump_json(),
                started_at.isoformat(),
                finished_at.isoformat(),
            ),
        )
        conn.executemany(
            "INSERT INTO endpoints (run_id, key_json, host, path_template, crypt, kind, zombie_candidate, record)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id,
                    key_json(record.key),
                    record.key.host,
                    record.key.path_template,
                    record.key.crypt,
                    record.kind,
                    None if record.zombie_candidate is None else int(record.zombie_candidate),
                    record.model_dump_json(),
                )
                for record in result.endpoints
            ],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO frontend_refs (run_id, key_json, script_key_json, seen_at) VALUES (?, ?, ?, ?)",
            [(run_id, key_json(ref.endpoint.key), key_json(ref.script_key), ref.seen_at.isoformat()) for ref in refs],
        )
