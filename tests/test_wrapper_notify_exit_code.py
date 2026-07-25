"""
tests/test_wrapper_notify_exit_code.py -- the wrapper's exit-code safety
property, proven against a notify_failure.py that crashes HARD.

test_notify_failure.py proves the well-behaved notify_failure.py never
raises. This file proves something stronger and different: even if
notify_failure.py were badly broken -- a bad top-level import, an
uncaught exception before its own try/except ever runs -- the CALLING
WRAPPER's exit code is still preserved. That guarantee lives in the
wrapper's own control flow (RC is captured BEFORE the notify call and
`exit /b !RC!` runs unconditionally afterward, never reading the notify
call's own errorlevel), not in anything notify_failure.py does. So this
test does not import or mock notify_failure.py at all -- it extracts the
literal failure-branch lines from the two real .bat files on disk and
executes them against a deliberately broken stand-in script.

Extracting the live text (rather than hand-copying a lookalike snippet)
means this test tracks the actual wrapper files: if someone edits the
failure branch and breaks the exit-code guarantee, this test breaks too.

NO LIVE NETWORK CALLS: the "notify" step here is a local Python file that
fails at import time, before any network code would run. No requests.post
is reachable from this path.

Status: E4 -- AI-drafted, pending Architect ratification (Invariant 3).
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REAL_PYTHON = _REPO_ROOT / "venv" / "Scripts" / "python.exe"

_WRAPPERS = [
    ("run_kalshi_observations.bat", "kalshi_observations"),
    ("run_cli_collection.bat", "cli_collection"),
]

# Matches from the "attempt 2 failed" log line through the final exit,
# i.e. exactly the block this task added the notify hook into.
_BLOCK_PATTERN = re.compile(
    r"echo \[%DATE% %TIME%\] FAILURE on attempt 2.*?exit /b !RC!",
    re.DOTALL,
)

_BROKEN_NOTIFY_SCRIPT = (
    "import this_module_absolutely_does_not_exist_xyz123\n"
)


def _extract_failure_block(wrapper_filename: str) -> str:
    text = (_REPO_ROOT / wrapper_filename).read_text(encoding="utf-8")
    match = _BLOCK_PATTERN.search(text)
    assert match, (
        f"could not find the attempt-2 failure block in {wrapper_filename} -- "
        "extraction pattern is stale, update it to match the current wrapper"
    )
    block = match.group(0)
    assert "notify_failure.py" in block, (
        f"extracted block from {wrapper_filename} does not call "
        "notify_failure.py -- the hook may have been removed"
    )
    return block


@pytest.mark.parametrize("wrapper_filename,wrapper_name", _WRAPPERS)
def test_wrapper_exit_code_survives_notify_hard_crash(wrapper_filename, wrapper_name):
    assert _REAL_PYTHON.exists(), (
        f"expected venv python at {_REAL_PYTHON} -- run the suite with "
        "venv/Scripts/python.exe per project convention"
    )

    failure_block = _extract_failure_block(wrapper_filename)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_repo = tmp_path / "fake_repo"
        (fake_repo / "scripts").mkdir(parents=True)
        (fake_repo / "scripts" / "notify_failure.py").write_text(
            _BROKEN_NOTIFY_SCRIPT, encoding="utf-8"
        )
        logfile = tmp_path / "harness.log"
        harness_bat = tmp_path / "harness.bat"

        harness_text = (
            "@echo off\n"
            "setlocal enabledelayedexpansion\n"
            f'set "REPO={fake_repo}"\n'
            f'set "PYTHON={_REAL_PYTHON}"\n'
            f'set "LOGFILE={logfile}"\n'
            'set "RC=7"\n'
            + failure_block
            + "\n"
        )
        harness_bat.write_text(harness_text, encoding="utf-8")

        result = subprocess.run(
            ["cmd.exe", "/c", str(harness_bat)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 7, (
            f"wrapper block from {wrapper_filename} did not preserve RC=7 "
            f"when notify_failure.py crashed hard: got returncode="
            f"{result.returncode}, stdout={result.stdout!r}, "
            f"stderr={result.stderr!r}"
        )

        log_text = logfile.read_text(encoding="utf-8", errors="replace")
        assert (
            "this_module_absolutely_does_not_exist_xyz123" in log_text
            or "ModuleNotFoundError" in log_text
            or "Traceback" in log_text
        ), (
            "expected evidence the stand-in notify script actually crashed "
            f"(not just skipped cleanly) in the captured log:\n{log_text}"
        )
