"""
tests/test_covered_day.py — F-01 regression: covered day comes from the CLI
body (header + block marker), never from the issuance timestamp.
Fixtures are the real captured PHX bodies (id5 summary, id4 preliminary),
both with header day JULY 15 2026.
"""
from pathlib import Path

from collectors.nws_cli_collector import (
    derive_covered_day,
    parse_report_kind,
    PARSER_VERSION,
)

FIX = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8", newline="")


def test_parser_version_is_2():
    assert PARSER_VERSION == "2"


def test_preliminary_covers_its_own_header_day():
    body = _load("cli_phx_preliminary_2026-07-15.txt")
    covered, marker, flag = derive_covered_day(body, "2026-07-15")
    assert covered == "2026-07-15"
    assert marker == "TODAY"
    assert flag == 0
    assert parse_report_kind(body) == "preliminary"


def test_summary_covers_the_prior_day_not_issuance_day():
    body = _load("cli_phx_summary_2026-07-15.txt")
    issuance_day = "2026-07-16"
    covered, marker, flag = derive_covered_day(body, issuance_day)
    assert covered == "2026-07-15"
    assert covered != issuance_day
    assert marker == "YESTERDAY"
    assert flag & 1
    assert not (flag & 2)
    assert parse_report_kind(body) == "summary"


def test_unparseable_header_returns_empty_not_a_guess():
    covered, marker, flag = derive_covered_day("garbage body no header", "2026-07-15")
    assert covered == ""
