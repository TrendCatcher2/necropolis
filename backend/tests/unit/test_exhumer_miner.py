"""JS mining (Req exhumer:4.3 to 4.6): examples, the demo site's own bundles, and the work bounds."""

from __future__ import annotations

import pytest

from necropolis.exhumer import Target, mine_js
from necropolis.exhumer import miner as miner_module
from necropolis.exhumer.miner import MAX_CANDIDATES, MAX_FOUND_PER_SCRIPT, MAX_LITERAL
from necropolis.normaliser import Normalised
from tests.archive_fake import demo_file

TARGET = Target(host="shop.example.com", registrable_domain="example.com")
SCRIPT = "https://shop.example.com/static/app.js"


def mined(text: str, *, script_url: str = SCRIPT, base_host: str | None = None) -> list[Normalised]:
    return mine_js(text, script_url, TARGET, base_host=base_host)


def paths(text: str, **kwargs: str | None) -> list[str]:
    return [endpoint.key.path_template for endpoint in mined(text, **kwargs)]  # type: ignore[arg-type]


def test_demo_front_end_v1() -> None:
    assert paths(demo_file("app.v1.js").decode()) == [
        "/api/v1/users/{id}",
        "/api/v1/orders",
        "/api/v1/status",
        "/api/v1/legacy-export",
        "/api/v1/debug/trace",
    ]


def test_demo_front_end_v2() -> None:
    assert paths(demo_file("app.v2.js").decode()) == ["/api/v2/session", "/api/v2/users/{id}", "/api/v2/orders"]


def test_template_literals_become_id_placeholders_without_an_example_path() -> None:
    (endpoint,) = mined("fetch(`/api/v1/users/${user.id}/orders/${ order }`)")  # Req 4.4
    assert endpoint.key.path_template == "/api/v1/users/{id}/orders/{id}"
    assert endpoint.example_path is None  # Req 5.3


def test_a_concrete_literal_keeps_its_example_path_and_only_parameter_names() -> None:
    (endpoint,) = mined('fetch("/api/v1/search?q=shoes&page=2")')
    assert endpoint.example_path == "/api/v1/search"
    assert endpoint.param_names == ("page", "q")
    assert "shoes" not in endpoint.model_dump_json()


@pytest.mark.parametrize(
    "text",
    [
        'fetch("/account/settings")',
        "axios.get('/account/settings')",
        "axios.post(`/account/settings`)",
        'client.get("/account/settings")',
        'api.post( "/account/settings", body)',
        'const request = { url: "/account/settings" }',
        '{url:"/account/settings"}',
    ],
)
def test_non_api_paths_need_a_request_call_just_before_them(text: str) -> None:
    assert paths(text) == ["/account/settings"]


@pytest.mark.parametrize(
    "text",
    [
        'const label = "/account/settings";',  # no request call
        'fetch(base + "/" + "/about")',  # one segment only
        'fetch("/about")',
        'fetch(x); /* ' + "-" * 40 + ' */ "/account/settings"',  # the call is too far back
    ],
)
def test_paths_without_that_context_are_skipped(text: str) -> None:
    assert paths(text) == []


def test_api_paths_need_no_context() -> None:
    source = 'const routes = ["/api/v3/cart", "/graphql", "/v1/users"];'
    assert paths(source) == ["/api/v3/cart", "/graphql", "/v1/users"]


def test_json_escaped_slashes() -> None:
    text = r'{"a":"\/api\/v1\/users","b":"/api/v1/items","c":"https:\/\/api.example.com\/v2\/x"}'
    assert [(e.key.host, e.key.path_template) for e in mined(text)] == [
        ("shop.example.com", "/api/v1/users"),
        ("shop.example.com", "/api/v1/items"),
        ("api.example.com", "/v2/x"),
    ]


def test_absolute_urls_on_the_site_are_kept_and_others_dropped() -> None:  # Req 4.5
    text = """
        fetch("https://api.example.com/v1/users");
        fetch("http://shop.example.com/api/v1/legacy");
        fetch("//cdn.example.com/api/v1/assets");
        fetch("https://api.other.example.org/v1/users");
        fetch("https://example.com.evil.example.net/api/v1/x");
        fetch("https://evil.example.net/?u=https://shop.example.com/api/v1/x");
        fetch("https://192.168.0.1/api/v1/x");
    """
    assert [(e.key.host, e.key.path_template, e.scheme) for e in mined(text)] == [
        ("api.example.com", "/v1/users", "https"),
        ("shop.example.com", "/api/v1/legacy", "http"),
        ("cdn.example.com", "/api/v1/assets", "https"),
    ]


def test_relative_paths_resolve_against_the_page_host_when_given() -> None:
    text = 'fetch("/api/v1/x")'
    assert mined(text, script_url="https://cdn.example.com/app.js")[0].key.host == "cdn.example.com"
    assert mined(text, script_url="https://cdn.example.com/app.js", base_host="shop.example.com")[0].key.host == (
        "shop.example.com"
    )


def test_relative_paths_are_skipped_when_there_is_no_host_to_resolve_them() -> None:
    text = 'fetch("/api/v1/x"); fetch("https://api.example.com/v1/y")'
    assert paths(text, script_url="not a url") == ["/v1/y"]


def test_literal_length_limit() -> None:
    body = "/api/" + "a" * (MAX_LITERAL - 5)
    assert len(body) == MAX_LITERAL
    assert len(paths(f'"{body}"')) == 1  # the long segment is templated; what matters is that it was read
    assert paths(f'"{body}a"') == []


def test_an_escaped_quote_ends_nothing_and_the_scan_goes_on() -> None:
    assert paths(r'x = "/api/v1/a\"b"; y = "/api/v1/next"') == ["/api/v1/next"]


def test_unresolvable_interpolations_are_skipped() -> None:
    assert paths("fetch(`/api/v1/${a{b}}/x`); fetch(`/api/v1/${`nested`}`)") == []


def test_a_minified_bundle() -> None:
    text = '!function(){var e="/api/v2/cart",t={url:"/checkout/confirm"};fetch(e).then(function(n){return n})}();'
    assert paths(text) == ["/api/v2/cart", "/checkout/confirm"]


def test_each_endpoint_once_in_order_of_first_appearance() -> None:
    text = 'fetch("/api/v1/b"); fetch("/api/v1/a"); fetch("/api/v1/b"); fetch(`/api/v1/a`)'
    assert paths(text) == ["/api/v1/b", "/api/v1/a"]


def test_normalising_is_bounded_per_script(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    real = miner_module.normalise

    def counting(raw: str, **kwargs: str | None) -> object:
        nonlocal calls
        calls += 1
        return real(raw, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(miner_module, "normalise", counting)
    text = ",".join(f'"/a{n}"' for n in range(3 * MAX_CANDIDATES)) + ',"/api/v1/late"'
    assert paths(text, base_host="shop.example.com") == []  # the budget ran out before the last literal
    assert calls == MAX_CANDIDATES
    calls = 0
    repeated = '"/a",' * (3 * MAX_CANDIDATES)
    paths(repeated, base_host="shop.example.com")
    assert calls == 1  # a literal seen before is not normalised again


def test_at_most_so_many_endpoints_per_script() -> None:
    text = ",".join(f'"/api/v{n}/x"' for n in range(MAX_FOUND_PER_SCRIPT + 100))
    assert len(mined(text)) == MAX_FOUND_PER_SCRIPT
