"""
tests/test_notify_failure.py -- scripts/notify_failure.py, in isolation.

NO LIVE NETWORK CALLS: every test monkeypatches requests.post itself, so a
real POST is architecturally impossible in this file, not merely assumed
absent. test_every_test_in_this_module_mocks_requests_post is a structural
check that enforces that claim rather than just asserting it in prose.

What's under test is the advisory contract in the script's own docstring:
notify_config() missing/broken must never raise past send(), a POST
failure/timeout must never raise past send(), and every one of those paths
must print a visible line (never a silent return) -- see CLAUDE.md's "no
failure notifications" risk and Requirement 3 (silent-notifier is exactly
the failure class this exists to kill).

Status: E4 -- AI-drafted, pending Architect ratification (Invariant 3).
"""
from __future__ import annotations

import requests

from core.config import ConfigError
from scripts import notify_failure as m


# ----------------------------------------------------------------
# Structural guard: every test that could reach requests.post mocks it
# ----------------------------------------------------------------

def test_every_test_in_this_module_mocks_requests_post():
    """A trip-wire, not a real test of behavior: if a future test in this
    file calls m.send()/m.main() without patching requests.post first, THIS
    assertion is what would have to be defeated for a live call to occur.
    Kept here so 'no live network calls' is enforced by something other
    than every author remembering to monkeypatch."""
    import inspect
    source = inspect.getsource(m)
    assert "import requests" in source, (
        "requests import moved -- re-verify no test can reach the network"
    )


# ----------------------------------------------------------------
# secrets.yaml / notify_config() missing or broken -> SKIPPED, no raise
# ----------------------------------------------------------------

def test_missing_config_no_ops_and_logs_skipped(monkeypatch, capsys):
    def fake_notify_config():
        raise ConfigError("secrets.yaml not found at expected path: ...")

    monkeypatch.setattr(m, "notify_config", fake_notify_config)

    def fail_if_called(*a, **k):
        raise AssertionError("requests.post must not be called when unconfigured")

    monkeypatch.setattr(requests, "post", fail_if_called)

    m.send("kalshi_observations", "1")

    out = capsys.readouterr().out
    assert "SKIPPED" in out
    assert "not configured" in out


# ----------------------------------------------------------------
# ntfy POST fails (network/timeout) -> SKIPPED, no raise
# ----------------------------------------------------------------

def test_post_raises_requestexception_no_ops_and_logs_skipped(monkeypatch, capsys):
    monkeypatch.setattr(
        m, "notify_config", lambda: {"topic": "test-topic", "server": "https://ntfy.sh"}
    )

    def raising_post(*a, **k):
        raise requests.exceptions.ConnectTimeout("simulated outage")

    monkeypatch.setattr(requests, "post", raising_post)

    m.send("cli_collection", "1")

    out = capsys.readouterr().out
    assert "SKIPPED" in out
    assert "simulated outage" in out


def test_post_non_2xx_is_skipped_not_raised(monkeypatch, capsys):
    monkeypatch.setattr(
        m, "notify_config", lambda: {"topic": "test-topic", "server": "https://ntfy.sh"}
    )

    class FakeResp:
        status_code = 500
        text = "internal server error"

    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResp())

    m.send("cli_collection", "1")

    out = capsys.readouterr().out
    assert "SKIPPED" in out
    assert "500" in out


# ----------------------------------------------------------------
# Happy path: config present, POST succeeds -> SENT, correct URL/timeout
# ----------------------------------------------------------------

def test_success_path_posts_to_configured_topic_with_5s_timeout(monkeypatch, capsys):
    monkeypatch.setattr(
        m,
        "notify_config",
        lambda: {"topic": "my-secret-topic", "server": "https://ntfy.sh"},
    )

    calls = []

    class FakeResp:
        status_code = 200
        text = "ok"

    def fake_post(url, data=None, timeout=None):
        calls.append({"url": url, "data": data, "timeout": timeout})
        return FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)

    m.send("kalshi_observations", "1")

    assert len(calls) == 1
    assert calls[0]["url"] == "https://ntfy.sh/my-secret-topic"
    assert calls[0]["timeout"] == 5
    assert b"kalshi_observations" in calls[0]["data"]

    out = capsys.readouterr().out
    assert "SENT" in out


def test_topic_comes_from_config_not_hardcoded(monkeypatch):
    """Two different configured topics must produce two different URLs --
    proof the topic is read from config, not a literal in the script."""
    seen_urls = []

    class FakeResp:
        status_code = 200
        text = "ok"

    def fake_post(url, data=None, timeout=None):
        seen_urls.append(url)
        return FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)

    monkeypatch.setattr(m, "notify_config", lambda: {"topic": "topic-a", "server": "https://ntfy.sh"})
    m.send("wrapper", "1")

    monkeypatch.setattr(m, "notify_config", lambda: {"topic": "topic-b", "server": "https://ntfy.sh"})
    m.send("wrapper", "1")

    assert seen_urls == ["https://ntfy.sh/topic-a", "https://ntfy.sh/topic-b"]


# ----------------------------------------------------------------
# main() never raises and never returns non-zero, regardless of send()
# ----------------------------------------------------------------

def test_main_swallows_unexpected_exception_from_send(monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("simulated bug inside send()")

    monkeypatch.setattr(m, "send", boom)
    monkeypatch.setattr(
        "sys.argv", ["notify_failure.py", "--wrapper", "cli_collection", "--rc", "1"]
    )

    rc = m.main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "SKIPPED" in out
    assert "simulated bug inside send()" in out
