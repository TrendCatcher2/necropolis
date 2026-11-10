"""Query parameter names (Req endpoint-normaliser:3.1 to 3.4). Values are cut off here and never decoded."""

from __future__ import annotations

import re
from urllib.parse import unquote

from necropolis.normaliser.segments import classify_segment

_NAME = re.compile(r"[A-Za-z0-9_.\-\[\]]{1,64}")


def query_names(query: str) -> tuple[str, ...]:
    """Req 3.1 and 3.3: valid names, decoded, unique and sorted.

    Req 3.4: a name that looks like a value (an id, hash, token, ... as in a bare `?<reset-token>`) is dropped too,
    because some apps put the secret in the name position.
    """
    names: set[str] = set()
    for pair in query.split("&"):
        name = unquote(pair.partition("=")[0])
        if _NAME.fullmatch(name) and classify_segment(name) is None:
            names.add(name)
    return tuple(sorted(names))
