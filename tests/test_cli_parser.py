"""tests/test_cli_parser.py — parser tests pinned to a real captured sample."""
import os
import pytest
from collectors.nws_cli_collector import (
    parse_high_low, parse_report_kind, _first_int_after_label,
)

SAMPLE_PATH = "sample_cli_phoenix.txt"


def test_max_line_shape():
    # The exact MAXIMUM line from the live PHX report (2026-07-13).
    line = "  MAXIMUM        108    449 PM 114    2005 107      1      108"
    assert _first_int_after_label(line) == 108


def test_missing_value_is_none():
    assert _first_int_after_label("  MAXIMUM         MM   ...") is None


@pytest.mark.skipif(not os.path.exists(SAMPLE_PATH),
                    reason="real sample not captured yet")
def test_real_sample_parses():
    text = open(SAMPLE_PATH, encoding="utf-8").read()
    high, low = parse_high_low(text)
    # High and low should be plausible Phoenix July temps and ordered.
    assert high is not None, "MAXIMUM not found in real sample"
    assert low is not None, "MINIMUM not found in real sample"
    assert 30 <= low <= high <= 130, f"implausible: high={high} low={low}"


@pytest.mark.skipif(not os.path.exists(SAMPLE_PATH),
                    reason="real sample not captured yet")
def test_report_kind_detected():
    text = open(SAMPLE_PATH, encoding="utf-8").read()
    assert parse_report_kind(text) in {"preliminary", "summary"}