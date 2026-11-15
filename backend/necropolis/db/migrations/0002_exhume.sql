-- Exhume runs and their results (exhumer design "Data Models"). No query values and no response bodies are stored
-- here (safety.md rule 5): endpoints carry templates, example paths without a query, and parameter names.
CREATE TABLE exhume_runs (
    id           TEXT PRIMARY KEY,
    host         TEXT NOT NULL,
    scope        TEXT NOT NULL CHECK (scope IN ('host', 'domain')),
    year_from    INTEGER,
    year_to      INTEGER,
    status       TEXT NOT NULL CHECK (status IN ('complete', 'partial', 'empty', 'cancelled')),
    failed_phase TEXT,
    capped       INTEGER NOT NULL,
    dating       TEXT NOT NULL,
    rejected     TEXT NOT NULL,  -- JSON {reason: count}
    scripts      TEXT NOT NULL,  -- JSON {picked, mined, failed}
    started_at   TEXT NOT NULL,
    finished_at  TEXT NOT NULL
);

CREATE TABLE endpoints (
    run_id           TEXT NOT NULL REFERENCES exhume_runs (id) ON DELETE CASCADE,
    key_json         TEXT NOT NULL,
    host             TEXT NOT NULL,
    path_template    TEXT NOT NULL,
    crypt            TEXT NOT NULL,
    kind             TEXT NOT NULL,
    zombie_candidate INTEGER,  -- 1, 0, or NULL when unknown
    record           TEXT NOT NULL,  -- the whole EndpointRecord as JSON
    PRIMARY KEY (run_id, key_json)
);
CREATE INDEX endpoints_host ON endpoints (host);

CREATE TABLE frontend_refs (
    run_id          TEXT NOT NULL REFERENCES exhume_runs (id) ON DELETE CASCADE,
    key_json        TEXT NOT NULL,
    script_key_json TEXT NOT NULL,
    seen_at         TEXT NOT NULL,
    PRIMARY KEY (run_id, key_json, script_key_json, seen_at)
);
