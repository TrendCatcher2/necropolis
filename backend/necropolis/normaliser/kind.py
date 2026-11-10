"""Endpoint kind: static, script, api or page (Req endpoint-normaliser:4.2 to 4.5)."""

from __future__ import annotations

from collections.abc import Sequence

from necropolis.normaliser.models import Kind

STATIC_EXTENSIONS: frozenset[str] = frozenset(
    {
        # images
        "apng", "avif", "bmp", "gif", "heic", "heif", "ico", "jpeg", "jpg", "png", "svg", "tif", "tiff", "webp",
        # fonts
        "eot", "otf", "ttf", "woff", "woff2",
        # stylesheets
        "css", "less", "sass", "scss",
        # media
        "aac", "avi", "flac", "m4a", "m4v", "mkv", "mov", "mp3", "mp4", "mpeg", "mpg", "oga", "ogg", "ogv", "opus",
        "wav", "weba", "webm",
        # source maps
        "map",
    }
)  # fmt: skip
SCRIPT_EXTENSIONS: frozenset[str] = frozenset({"js", "mjs"})
API_EXTENSIONS: frozenset[str] = frozenset({"json", "xml", "php", "asp", "aspx", "jsp", "do"})
API_SEGMENTS: frozenset[str] = frozenset({"api", "rest", "graphql", "rpc", "ajax", "json", "ws"})
FILE_EXTENSIONS: frozenset[str] = STATIC_EXTENSIONS | SCRIPT_EXTENSIONS | API_EXTENSIONS

_MAX_MIMETYPE = 255


def extension(segment: str) -> str:
    """The lowercased text after the last dot of a segment, or "" when there is none."""
    _, dot, ext = segment.rpartition(".")
    return ext.lower() if dot else ""


def is_json_or_xml(mimetype: str | None) -> bool:
    """Req 4.4: a JSON or XML capture MIME type (application/json, text/xml, application/vnd.api+json, ...)."""
    if not mimetype or len(mimetype) > _MAX_MIMETYPE:
        return False
    essence = mimetype.partition(";")[0].strip().lower()
    top, slash, sub = essence.partition("/")
    if not slash or top not in ("application", "text") or sub == "xhtml+xml":  # XHTML is a page
        return False
    return sub in ("json", "x-json", "xml") or sub.endswith(("+json", "+xml"))


def kind_of(segments: Sequence[str], *, has_version: bool, mimetype: str | None) -> Kind:
    """Classify a templated path. Checked in the order of Req 4.2 to 4.5, so `/api/v1/logo.png` is static."""
    ext = extension(segments[-1]) if segments else ""
    if ext in STATIC_EXTENSIONS:
        return "static"
    if ext in SCRIPT_EXTENSIONS:
        return "script"
    if (
        ext in API_EXTENSIONS
        or has_version
        or any(segment.lower() in API_SEGMENTS for segment in segments)
        or is_json_or_xml(mimetype)
    ):
        return "api"
    return "page"
