-- Archive cache (Req exhumer:3.3, safety.md rule 6): CDX listings and raw snapshots, kept for 7 days.
-- req_hash is a SHA-256 of the request. CDX listings are stored with query values removed (safety.md rule 5);
-- snapshot bodies are the archived files themselves, decoded and capped at 2 MiB.
CREATE TABLE archive_cache (
    req_hash   TEXT PRIMARY KEY,
    body       BLOB NOT NULL,  -- zlib-compressed
    meta       TEXT NOT NULL,  -- JSON
    fetched_at TEXT NOT NULL   -- UTC, ISO 8601
);
CREATE INDEX archive_cache_fetched_at ON archive_cache (fetched_at);
