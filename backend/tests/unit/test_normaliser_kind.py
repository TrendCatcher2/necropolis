"""Req endpoint-normaliser:4.1 to 4.5: crypt and kind."""

from __future__ import annotations

import pytest

from necropolis.normaliser import Normalised, crypt_of, normalise


def normalised(path: str, mimetype: str | None = None) -> Normalised:
    result = normalise("https://example.com" + path, mimetype=mimetype)
    assert isinstance(result, Normalised), result
    return result


@pytest.mark.parametrize(
    ("path", "crypt"),
    [
        ("/api/v1/users", "v1"),
        ("/api/V2/users", "v2"),  # lowercased, so /API/V2 and /api/v2 share a crypt
        ("/v2.1/x", "v2.1"),
        ("/api/v1/v2/x", "v1"),  # 4.1 the first one
        ("/api/users", "unversioned"),
        ("/v1.2.3/x", "unversioned"),
        ("/static/app.v1.js", "unversioned"),  # not a segment of its own
    ],
)
def test_crypt(path: str, crypt: str) -> None:
    assert normalised(path).key.crypt == crypt


def test_crypt_of() -> None:
    assert crypt_of(["api", "V3", "v4"]) == "v3"
    assert crypt_of([]) == "unversioned"


@pytest.mark.parametrize(
    ("path", "mimetype", "kind"),
    [
        ("/img/logo.png", None, "static"),  # 4.2
        ("/fonts/inter.woff2", None, "static"),
        ("/css/site.CSS", None, "static"),
        ("/media/intro.mp4", None, "static"),
        ("/static/app.js.map", None, "static"),  # source map
        ("/api/v1/docs/logo.png", None, "static"),  # 4.2 is checked before 4.4
        ("/static/app.v1.js", None, "script"),  # 4.3
        ("/m/module.mjs", None, "script"),
        ("/api/x", None, "api"),  # 4.4 segments
        ("/rest/x", None, "api"),
        ("/graphql", None, "api"),
        ("/rpc/x", None, "api"),
        ("/ajax/x", None, "api"),
        ("/json/x", None, "api"),
        ("/ws/x", None, "api"),
        ("/API/x", None, "api"),
        ("/v1/x", None, "api"),  # 4.4 version segment
        ("/data/feed", "application/json", "api"),  # 4.4 MIME type
        ("/data/feed", "application/vnd.api+json; charset=utf-8", "api"),
        ("/data/feed", "text/xml", "api"),
        ("/feed.xml", None, "api"),  # 4.4 extensions
        ("/index.php", None, "api"),
        ("/default.aspx", None, "api"),
        ("/legacy.asp", None, "api"),
        ("/login.jsp", None, "api"),
        ("/cart.do", None, "api"),
        ("/data.json", None, "api"),
        ("/", None, "page"),  # 4.5
        ("/about", None, "page"),
        ("/blog/hello-world", None, "page"),
        ("/data/feed", "text/html", "page"),
        ("/data/feed", "image/svg+xml", "page"),  # an image, not an API answer
        ("/data/feed", "application/xhtml+xml", "page"),
        ("/data/feed", "warc/revisit", "page"),
        ("/users/{email}", None, "page"),  # kind comes from the template, not from a value like logo@2x.png
    ],
)
def test_kind(path: str, mimetype: str | None, kind: str) -> None:
    assert normalised(path, mimetype).kind == kind
