"""Req endpoint-normaliser:2.3, 2.4, 5.1, 5.3: the public API, the models and purity by construction."""

from __future__ import annotations

import ast
from pathlib import Path

import pydantic
import pytest

import necropolis.normaliser
from necropolis.normaliser import EndpointKey, Normalised, normalise, render


def accepted(raw: str, **kwargs: str) -> Normalised:
    result = normalise(raw, **kwargs)
    assert isinstance(result, Normalised), result
    return result


def test_the_intro_example_is_one_tombstone() -> None:
    """requirements.md introduction: these must become one key, /api/v1/users/{id}."""
    one = accepted("https://example.com/api/v1/users/123?ref=mail")
    two = accepted("https://example.com/api/v1/users/9876")
    assert one.key == two.key
    assert one.key.path_template == "/api/v1/users/{id}"


def test_old_http_and_new_https_captures_share_a_key() -> None:
    old = accepted("http://example.com/api/v1/users/1")
    new = accepted("https://example.com:443/api/v1/users/2")
    assert old.key == new.key
    assert (old.scheme, new.scheme) == ("http", "https")


def test_values_of_every_class_collapse() -> None:
    """2.3"""
    one = accepted("https://example.com/api/v1/orders/2024-01-31/items/550e8400-e29b-41d4-a716-446655440000/42")
    two = accepted("https://example.com/api/v1/orders/1999-12-01/items/6BA7B810-9DAD-11D1-80B4-00C04FD430C8/7")
    assert one.key == two.key
    assert one.key.path_template == "/api/v1/orders/{date}/items/{uuid}/{id}"


def test_example_path() -> None:
    """2.4: the concrete path, without query or fragment."""
    assert accepted("https://example.com/api/v1/users/123/?ref=mail#top").example_path == "/api/v1/users/123"
    assert accepted("https://example.com").example_path == "/"


@pytest.mark.parametrize("path", ["/api/v1/users/{id}", "/api/v1/users/user-{id}/x"])
def test_no_example_path_when_the_input_held_placeholders(path: str) -> None:
    """A JS path such as `/api/v1/users/${id}` (the exhumer writes {id}) is not a concrete path to probe."""
    assert accepted(path, base_host="example.com").example_path is None


def test_render() -> None:
    """5.3"""
    result = accepted("http://Example.com:8080/a/1/?b=2&a=1#x")
    assert render(result.key) == "https://example.com:8080/a/{id}"
    assert render(result.key, scheme=result.scheme, param_names=result.param_names) == (
        "http://example.com:8080/a/{id}?a&b"
    )
    assert accepted(render(result.key)).key == result.key


def test_models_are_frozen_and_hashable() -> None:
    key = accepted("https://example.com/api/v1/users/1").key
    assert {key: "tombstone"}[accepted("https://example.com/api/v1/users/2").key] == "tombstone"
    with pytest.raises(pydantic.ValidationError):
        key.host = "example.org"  # type: ignore[misc]
    with pytest.raises(pydantic.ValidationError):
        EndpointKey(host="example.com", port=None, path_template="/", crypt="unversioned", scheme="https")  # type: ignore[call-arg]


_ALLOWED_IMPORTS = {"__future__", "collections.abc", "dataclasses", "enum", "re", "typing", "urllib.parse",
                    "idna", "tldextract", "pydantic"}  # fmt: skip
_FORBIDDEN_CALLS = {"open", "print", "input", "eval", "exec", "__import__", "breakpoint"}


@pytest.mark.parametrize("source", sorted(Path(necropolis.normaliser.__file__).parent.glob("*.py")), ids=str)
def test_normaliser_imports_nothing_impure(source: Path) -> None:
    """5.1 by construction: no os, io, time, random, socket, ... and no open() or print()."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        else:
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in _FORBIDDEN_CALLS, f"{source.name}:{node.lineno} calls {node.func.id}"
            continue
        for module in modules:
            internal = module.startswith("necropolis.normaliser")
            assert internal or module in _ALLOWED_IMPORTS, f"{source.name}:{node.lineno} imports {module}"
