"""CDX JSON parsing and query building (Req exhumer:2.1, 2.2, 2.4; safety.md rule 5)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import httpx
import pytest

from necropolis.archive import CdxFormatError, CdxQuery, cdx_target, parse_page, url_sha256

HEADER = ["timestamp", "original", "mimetype", "statuscode"]
COUNTERS = [*HEADER, "skipcount", "endtimestamp"]
T1 = datetime(2023, 1, 10, 10, 16, 36, tzinfo=UTC)


def page(*rows: object) -> bytes:
    return json.dumps(list(rows)).encode()


def test_header_and_rows() -> None:
    result = parse_page(
        page(
            HEADER,
            ["20230110101636", "https://shop.example.com/", "text/html", "200"],
            ["20230110102038", "https://shop.example.com/api/v1/users/2", "application/json", "404"],
        )
    )
    assert result.malformed == 0
    assert result.resume_key is None
    assert not result.counters
    first, second = result.rows
    assert first.timestamp == T1
    assert first.last_timestamp == T1
    assert first.captures == 1
    assert first.original == "https://shop.example.com/"
    assert first.mimetype == "text/html"
    assert first.status == 200
    assert second.status == 404


def test_counters_extend_a_collapsed_row() -> None:
    result = parse_page(
        page(
            COUNTERS,
            ["20230110101636", "https://shop.example.com/a", "text/html", "200", "4", "20240301120000"],
            ["20230110101636", "https://shop.example.com/b", "text/html", "200", 2, "20230110101636"],
        )
    )
    assert result.counters
    a, b = result.rows
    assert a.captures == 5
    assert a.last_timestamp == datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC)
    assert b.captures == 3


@pytest.mark.parametrize(("skip", "end"), [("-", "-"), ("abc", "2024"), ("", ""), (None, None), ("-1", "x" * 14)])
def test_unreadable_counters_fall_back_to_the_row_itself(skip: object, end: object) -> None:
    result = parse_page(page(COUNTERS, ["20230110101636", "https://shop.example.com/a", "text/html", "200", skip, end]))
    (row,) = result.rows
    assert (row.captures, row.last_timestamp) == (1, T1)


def test_an_end_before_the_first_capture_never_moves_last_seen_back() -> None:
    result = parse_page(
        page(COUNTERS, ["20230110101636", "https://shop.example.com/a", "text/html", "200", "1", "20200101000000"])
    )
    assert result.rows[0].last_timestamp == T1


def test_counters_need_both_columns() -> None:
    result = parse_page(page([*HEADER, "skipcount"], ["20230110101636", "https://shop.example.com/a", "-", "-", "3"]))
    assert not result.counters
    assert result.rows[0].captures == 1


def test_resume_key_after_an_empty_row() -> None:
    result = parse_page(
        page(
            HEADER, ["20230110101636", "https://shop.example.com/", "text/html", "200"], [], ["com,example%29%2F+2023"]
        )
    )
    assert len(result.rows) == 1
    assert result.resume_key == "com,example%29%2F+2023"
    assert "com,example" not in repr(result)  # the key can hold a query value: never printed


def test_a_page_of_only_a_resume_key() -> None:
    result = parse_page(page(HEADER, [], ["next"]))
    assert result.rows == ()
    assert result.resume_key == "next"


@pytest.mark.parametrize("body", [b"[]", b"[]\n", page(HEADER)])
def test_empty_answers(body: bytes) -> None:
    result = parse_page(body)
    assert result.rows == ()
    assert result.resume_key is None


def test_header_names_are_matched_by_name_in_any_order_and_case() -> None:
    result = parse_page(
        page(
            ["Original", "StatusCode", "length", "TIMESTAMP", "mimetype"],
            ["https://shop.example.com/x", "301", "123", "20230110101636", "text/html"],
        )
    )
    (row,) = result.rows
    assert (row.original, row.status, row.timestamp) == ("https://shop.example.com/x", 301, T1)


@pytest.mark.parametrize(
    "bad",
    [
        ["20230110101636", "https://shop.example.com/"],  # short
        ["2023", "https://shop.example.com/", "text/html", "200"],  # timestamp not 14 digits
        ["20231310101636", "https://shop.example.com/", "text/html", "200"],  # month 13
        ["20230110101636", 42, "text/html", "200"],  # original not a string
        ["20230110101636", "", "text/html", "200"],  # empty original
        ["20230110101636", "https://shop.example.com/" + "a" * 8200, "text/html", "200"],  # absurdly long
        "not a row",
        None,
        {"timestamp": "20230110101636"},
    ],
)
def test_malformed_rows_are_counted_not_fatal(bad: object) -> None:
    result = parse_page(page(HEADER, bad, ["20230110101636", "https://shop.example.com/", "text/html", "200"]))
    assert result.malformed == 1
    assert len(result.rows) == 1


@pytest.mark.parametrize(
    ("status", "expected"),
    [("200", 200), ("404", 404), ("-", None), ("", None), ("2000", None), ("099", None), ("600", None), (200, None)],
)
def test_status_codes(status: object, expected: int | None) -> None:
    result = parse_page(page(HEADER, ["20230110101636", "https://shop.example.com/", "text/html", status]))
    assert result.rows[0].status == expected


@pytest.mark.parametrize(("mimetype", "expected"), [("-", None), ("", None), (None, None), ("text/html", "text/html")])
def test_mimetype_placeholders(mimetype: object, expected: str | None) -> None:
    result = parse_page(page(HEADER, ["20230110101636", "https://shop.example.com/", mimetype, "200"]))
    assert result.rows[0].mimetype == expected


def test_query_values_are_removed_before_anything_sees_the_row() -> None:
    raw = "https://user:pw@shop.example.com/static/app.js?v=SECRETVALUE&debug#frag"
    (row,) = parse_page(page(HEADER, ["20230110101636", raw, "application/javascript", "200"])).rows
    assert row.original == "https://shop.example.com/static/app.js?debug&v"
    assert row.query_stripped
    assert row.original_sha256 == hashlib.sha256(raw.encode()).hexdigest()
    assert row.address() == raw  # in memory only, to fetch the snapshot
    for shown in (repr(row), str(row), row.model_dump_json(), json.dumps(row.model_dump(mode="json"))):
        assert "SECRETVALUE" not in shown
        assert "pw@" not in shown


def test_a_row_without_query_values_addresses_itself() -> None:
    (row,) = parse_page(page(HEADER, ["20230110101636", "https://shop.example.com/a?debug", "text/html", "200"])).rows
    assert not row.query_stripped
    assert row.raw_original is None
    assert row.address() == "https://shop.example.com/a?debug"


@pytest.mark.parametrize(
    "body",
    [b"", b"not json", b"\xff\xfe\x00", b"{}", b'"text"', b"42", page(["timestamp", "original"]), page([1, 2, 3, 4])],
)
def test_answers_that_are_not_the_cdx_shape(body: bytes) -> None:
    with pytest.raises(CdxFormatError):
        parse_page(body)


def test_absurd_nesting_is_a_format_error_not_a_crash() -> None:
    with pytest.raises(CdxFormatError):
        parse_page(b"[" * 200_000)


def test_url_sha256_names_the_url_as_archived() -> None:
    assert url_sha256("https://shop.example.com/a?x=1") == hashlib.sha256(b"https://shop.example.com/a?x=1").hexdigest()


def test_listing_query_params() -> None:
    query = CdxQuery.listing("shop.example.com", match_type="host")
    assert query.params() == [
        ("url", "shop.example.com"),
        ("matchType", "host"),
        ("output", "json"),
        ("fl", "timestamp,original,mimetype,statuscode"),
        ("collapse", "urlkey"),
        ("showSkipCount", "true"),
        ("lastSkipTimestamp", "true"),
        ("limit", "5000"),
        ("showResumeKey", "true"),
    ]


def test_listing_query_with_years_and_domain_scope() -> None:
    params = CdxQuery.listing("example.com", match_type="domain", years=(2019, 2023)).params()
    assert ("matchType", "domain") in params
    assert ("from", "2019") in params
    assert ("to", "2023") in params


def test_newest_root_query() -> None:
    params = CdxQuery.newest_root("shop.example.com").params()
    assert ("url", "shop.example.com/") in params
    assert ("matchType", "exact") in params
    assert ("filter", "statuscode:200") in params
    assert ("filter", "mimetype:text/html") in params
    assert ("limit", "-3") in params
    assert ("collapse", "urlkey") not in params
    assert all(name != "showResumeKey" for name, _ in params)  # no resume key with a negative limit


def test_resume_key_is_sent_back_verbatim() -> None:
    key = "com%2Cexample%29%2Fstatic%2Fapp.js%3Fv%3D2+20230110101636"
    target = cdx_target(CdxQuery.listing("shop.example.com", match_type="host"), key)
    assert target.endswith("&resumeKey=" + key)
    request = httpx.Client(base_url="https://web.archive.org").build_request("GET", target)
    assert request.url.raw_path.decode("ascii").endswith("&resumeKey=" + key)


def test_resume_key_characters_outside_the_url_set_are_escaped() -> None:
    target = cdx_target(CdxQuery.listing("shop.example.com", match_type="host"), "a b&c")
    assert target.endswith("&resumeKey=a%20b%26c")
