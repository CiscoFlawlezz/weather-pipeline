"""
tests/test_notify_failure_real_invocation.py -- reproduces, and proves
fixed, the exact bug found during induced-failure verification.

The wrapper invokes scripts/notify_failure.py by ABSOLUTE PATH via
subprocess, from whatever cwd Task Scheduler happens to be in -- never
`python -m`, never guaranteed to be repo root (the cd-failure branch calls
it BEFORE cd succeeds). Running the real file that way previously raised
ModuleNotFoundError: No module named 'core', because Python puts the
script's own directory on sys.path[0], not the repo root, when a script is
run by path. tests/test_notify_failure.py imports the module directly, so
pytest's own sys.path (repo root) masked this completely -- that gap is
exactly why this file exists as a SEPARATE test: it invokes the real file
as a subprocess, no module import, no stand-in script.

NO LIVE NETWORK CALL: the induced-failure path genuinely imports core and
reads the real, gitignored secrets.yaml (per the Architect's design --
there is no test-only config seam). This test temporarily backs up that
file, points ntfy_server at a local HTTP server bound to 127.0.0.1 for the
duration of the subprocess call only, and restores the original content
(or removes the file if none existed) in a finally block regardless of
outcome. "No live network call" is PROVEN, not assumed: the assertion
checks that the local sink server itself received exactly one POST with
the expected path and body -- if the request had gone anywhere else, the
local server would have received nothing and the test would fail.

Status: E4 -- AI-drafted, pending Architect ratification (Invariant 3).
"""
from __future__ import annotations

import http.server
import subprocess
import threading
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REAL_PYTHON = _REPO_ROOT / "venv" / "Scripts" / "python.exe"
_REAL_SCRIPT = _REPO_ROOT / "scripts" / "notify_failure.py"
_REAL_SECRETS = _REPO_ROOT / "secrets.yaml"

_SINK_TOPIC = "regression-test-sink-topic"


class _CapturingHandler(http.server.BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _CapturingHandler.received.append({"path": self.path, "body": body})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):  # noqa: A002 -- stdlib signature
        pass  # keep pytest output clean; nothing here is a test failure signal


def test_real_script_survives_absolute_path_invocation_from_outside_repo(tmp_path):
    assert _REAL_PYTHON.exists(), f"expected venv python at {_REAL_PYTHON}"
    assert _REAL_SCRIPT.exists(), f"expected real script at {_REAL_SCRIPT}"

    _CapturingHandler.received = []
    server = http.server.HTTPServer(("127.0.0.1", 0), _CapturingHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    had_real_secrets = _REAL_SECRETS.exists()
    real_secrets_backup = _REAL_SECRETS.read_bytes() if had_real_secrets else None

    outside_cwd = tmp_path / "definitely_not_the_repo_root"
    outside_cwd.mkdir()

    try:
        # Point at the LOCAL sink only -- never the real configured topic,
        # never the real ntfy.sh. This is the "pointed at a sink" proof.
        _REAL_SECRETS.write_text(
            "notify:\n"
            f'  ntfy_topic: "{_SINK_TOPIC}"\n'
            f'  ntfy_server: "http://127.0.0.1:{port}"\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                str(_REAL_PYTHON),
                str(_REAL_SCRIPT),  # absolute path, exactly as the wrapper calls it
                "--wrapper", "regression_test",
                "--rc", "1",
            ],
            cwd=str(outside_cwd),  # deliberately NOT the repo root
            capture_output=True,
            text=True,
            timeout=30,
        )
    finally:
        server.shutdown()
        server.server_close()
        if had_real_secrets:
            _REAL_SECRETS.write_bytes(real_secrets_backup)
        else:
            _REAL_SECRETS.unlink(missing_ok=True)

    # --- The bug this test exists to catch ---------------------------
    assert "ModuleNotFoundError" not in result.stderr, (
        "the real script still fails to import 'core' when invoked by "
        f"absolute path from outside the repo:\nstderr={result.stderr}"
    )
    assert result.returncode == 0, (
        f"unexpected exit code {result.returncode}: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "SENT" in result.stdout, (
        f"expected a SENT confirmation line, got stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )

    # --- Proof (not assumption) that the POST hit ONLY the local sink -
    assert len(_CapturingHandler.received) == 1, (
        "expected exactly one POST received by the local sink server; "
        f"got {len(_CapturingHandler.received)} -- if 0, the request never "
        "reached even the sink (investigate before trusting this test); if "
        ">1, something is retrying or duplicating"
    )
    received = _CapturingHandler.received[0]
    assert received["path"] == f"/{_SINK_TOPIC}"
    assert b"regression_test" in received["body"]
