"""CDX rows for a target, normalised (Req exhumer:2.1 to 2.4)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from necropolis.archive import ArchiveClient, CaptureRow, CdxQuery, CdxStats
from necropolis.exhumer.models import Capture, Target
from necropolis.normaliser import Rejected, normalise, registrable_domain

CDX_CAP = 200_000  # Req 2.3: rows per run


async def cdx_captures(
    client: ArchiveClient,
    target: Target,
    years: tuple[int, int] | None = None,
    *,
    stats: CdxStats | None = None,
    cap: int = CDX_CAP,
) -> AsyncIterator[CaptureRow]:
    """Every CDX row for the target's scope, page by page via resume keys, until no key is left or `cap` rows."""
    query = CdxQuery.listing(target.host, match_type="host" if target.scope == "host" else "domain", years=years)
    async for row in client.cdx_rows(query, cap=cap, stats=stats):
        yield row


def to_capture(row: CaptureRow, target: Target) -> Capture | str:
    """Req 2.4: the row normalised, or the reason it was rejected (counted, never fatal)."""
    result = normalise(row.original, mimetype=row.mimetype)
    if isinstance(result, Rejected):
        return result.reason
    if registrable_domain(result.key.host) != target.registrable_domain:
        return "off_site"  # the archive answered with a row from another site: never inventoried
    return Capture(
        endpoint=result,
        first_seen=row.timestamp,
        last_seen=row.last_timestamp,
        count=row.captures,
        status=row.status,
        mimetype=row.mimetype,
    )
