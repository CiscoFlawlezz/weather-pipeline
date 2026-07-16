---
title: Session Log — 2026-07-16 — M2 Expansion: Five-City Collection
status: E4 — AI-drafted testimony, pending Architect ratification (Invariant 3)
scope: weather-pipeline; collectors/nws_cli_collector.py __main__ + new test file
outcome: COMPLETE. One scheduled execution collects Phoenix, NYC, Chicago, Miami, Austin.
next_step: Architect ratification. Then F3 (11am ET rule) or Kalshi market collectors.
---

# Session Log — 2026-07-16 — M2 Expansion

**Task:** replace the Phoenix-only hardcode with configuration-driven collection
of every configured city, preserving every existing guarantee.

**Result: DONE.** All five cities collect in one scheduled execution. The
accrual clock is now live for five cities instead of one.

**Commit:** `757df5b` (not pushed at time of writing).
**Suite:** 37 → **48 passed**. No pre-existing test modified.

---

## 1. Result in one paragraph

`collect_city()` was **not touched** — verified programmatically as
byte-identical (1796 bytes, both sides). Two functions were added after it:
`collect_all(db_path)`, which iterates `config.cities()` and isolates per-city
failures, and `exit_code_for(results)`, which returns 0 only if every city
succeeded. `__main__` went from one line (`print(collect_city("phoenix", db))`)
to three (collect, print each, exit). The wrapper and the three Task Scheduler
XMLs were **not modified** — and that was *proven* by running the real wrapper,
not asserted. Live verification: five cities stored on run 1, five skipped on
run 2, row count 9 → 9.

---

## 2. What changed

### `collectors/nws_cli_collector.py`

Added `from typing import NamedTuple`. Added after `collect_city`:

```python
class CityResult(NamedTuple):
    city: str
    ok: bool
    message: str

def collect_all(db_path: str) -> list[CityResult]:
    results = []
    for city in config.cities():
        try:
            results.append(CityResult(city, True, collect_city(city, db_path)))
        except Exception as exc:
            results.append(CityResult(
                city, False, f"{city}: FAILED - {type(exc).__name__}: {exc}"))
    return results

def exit_code_for(results) -> int:
    return 0 if all(r.ok for r in results) else 1
```

`__main__` now calls `collect_all(db)`, prints each `r.message`, and
`sys.exit(exit_code_for(results))`.

### `tests/test_collect_all.py` (new, 11 tests, no network)

### NOT changed
`collect_city`, the parser, the schema, `run_cli_collection.bat`, the three
scheduler XMLs, `config.yaml`, and every pre-existing test.

---

## 3. Design decisions and their reasons

### Why `collect_all()` rather than a loop inside `__main__`

The Architect asked directly whether `collect_all()` was the smallest change or
an unnecessary abstraction. The smaller alternative (loop inline in `__main__`,
~8 lines, no new function) satisfies requirements 1–6 **behaviorally** but is
**unreachable by pytest** — code under `if __name__ == "__main__":` cannot be
imported. Testing requirements 4/5/6 would then require `subprocess` for every
test, and mocking cannot cross a process boundary, so "Chicago fails, other four
still collect" would be untestable without real network manipulation.

`collect_all()` is not abstraction for elegance. It is the minimum move that
makes the loop **return data instead of printing and exiting**, which is what
makes it testable. Accepted on that basis.

### Failure semantics — read from the artifact, not inferred

`collect_city` (lines 79–120) has **two success paths, both `return`**:
- line 93 — duplicate: `return f"{city}: product {product_id} already stored - skipped"`
- line 117 — stored: `return f"{city}: stored {product_id} | ..."`

**Failure is by exception only.** Nothing in the function catches anything;
`finally: conn.close()` closes but does not swallow. Therefore: **a returned
string always means success (stored OR skipped); an exception always means
failure.** There is no ambiguous case, which is why `try/except Exception` per
city is the correct and complete isolation.

### ConfigError is treated like any other failure (Architect ruling)

Rationale, per Architect: attempt every configured city, maximize
non-backfillable accrual, report truthfully. A malformed config for Chicago must
not prevent Phoenix, NYC, Miami and Austin from collecting. Record Chicago
failed, continue, exit non-zero. Tested:
`test_config_error_isolates_like_any_other_failure`.

### A duplicate skip is a SUCCESS

`collect_city` returns normally on a duplicate; the row is present; nothing
failed. Treating a skip as failure would make every post-first-run sweep exit
non-zero, triggering the wrapper's retry and eventually a Task Scheduler failure
on a *correctly functioning* system. Tested: `test_duplicate_skip_counts_as_success`.

### Wrapper interaction, stated in advance and confirmed

The wrapper retries the **whole run** once on non-zero. If Chicago fails and the
other four succeed → exit 1 → attempt 2 re-runs all five → four skip as
duplicates (idempotent, harmless) and Chicago gets a genuine second chance.
This is desirable and needs **no wrapper change**. The wrapper is already
city-agnostic: it calls `python -m collectors.nws_cli_collector "%DB%"` and knows
nothing about Phoenix. (Its header *comment* says "Phoenix collector" — a comment,
not logic. Out of scope.)

---

## 4. Test coverage (`tests/test_collect_all.py`, 11 tests, zero network)

| # | Requirement | Test |
|---|---|---|
| 1 | Phoenix still succeeds | `test_phoenix_still_succeeds` |
| 2 | All five collect | `test_collect_all_attempts_every_configured_city`, `test_collect_all_includes_all_five_named_cities` |
| 3 | Duplicate detection works | `test_duplicate_skip_counts_as_success` |
| 4 | Chicago fails → other four still collect | `test_chicago_failure_does_not_stop_other_cities`, `test_config_error_isolates_like_any_other_failure`, `test_every_city_failing_still_attempts_all_five`, `test_failure_message_names_the_exception` |
| 5 | Exit non-zero if any failed | `test_exit_code_nonzero_when_any_city_failed` |
| 6 | Exit zero only when all succeed | `test_exit_code_zero_when_all_succeed` |
| — | db_path passes through unchanged | `test_collect_all_passes_db_path_through` |

Requirement 2 is tested against `config.cities()` — the test asserts the
attempted list *equals config*, so a hardcoded literal in the implementation
would fail it.

`__main__` is **deliberately untested**. See §5.1.

---

## 5. Incidents and corrections

### 5.1 A "mocked" test made a live network call — CAUGHT

The first version of `test_collect_all.py` included two `subprocess` tests that
used `runpy.run_module("collectors.nws_cli_collector", run_name="__main__")`
after patching `m.collect_city`.

**`runpy.run_module` re-imports the module from source.** It creates a *second*
module object. The patch landed on the first; `__main__` used the second. The
mock never applied, and the test **silently called api.weather.gov for real**.

Caught by the failure output, which contained a real Phoenix UUID
(`f59b81a0-...`), a real `high=109`, and `climate_day 2026-07-16` — data no mock
produced. Python's own warning in the same output named the cause: the module was
imported and then executed again under `__main__`.

**Damage assessment (run before proceeding):** `data/pipeline.db` had 4 rows, all
KPHX, none from the test; file mtime predated the run. The test used
`tmp_path/test.db`, so nothing was written to the real DB. It did make one
unnecessary request to weather.gov, fetching a product that was already stored.
**No data harm.**

**Resolution (Architect chose Option A):** both subprocess tests removed. The
exit-code *contract* is fully tested via `exit_code_for()` directly. `__main__`
is three lines, correct by inspection, and confirmed by the live run (§6).

**Lesson:** a test that can silently reach production is a bad test regardless of
whether it passes. `runpy` + monkeypatch do not compose.

### 5.2 Byte-identity check crashed — the check never ran

The first `collect_city`-identity check used an `extract()` that looked for the
next `\ndef ` or `\nclass `. In the **old** file `collect_city` is the last
function — followed only by `if __name__`. `ValueError: substring not found`.

**The check reported nothing rather than reporting False.** Same class of error
as 2026-07-15's `/tmp` diff: a verification that silently did not execute.
Rewritten to search for `\ndef `, `\nclass `, **and** `\nif __name__`, taking the
earliest. Then it ran: **`collect_city IDENTICAL: True`, 1796 bytes both sides.**

### 5.3 DISCOVERY: the repo is being auto-committed AND auto-pushed

`git log` revealed commits neither party wrote:

```
afc8449 (HEAD -> main, origin/main) Auto-backup: Thu 07/16/2026 13:14:30.87
81ff520 Auto-backup: Thu 07/16/2026  0:29:49.55
b783f6c Auto-backup: Tue 07/14/2026 12:14:31.95
67f495e Auto-backup: Tue 07/14/2026  0:14:31.90
```

Roughly twice daily (~00:14 and ~12:14/13:14). Architect confirmed: **a Windows
Task Scheduler auto-backup task built in an earlier session.** No git hooks
(`.git/hooks/` is empty of non-samples); the script lives outside the repo, which
is why an in-repo grep for "Auto-backup" found nothing.

**Not a defect — it is the R5 backup working.** But three consequences:

1. **It commits and pushes broken intermediate states.** `afc8449` captured
   `test_collect_all.py` *with the subprocess tests still in it* — the ones that
   called the live API. That state is on `origin/main`. Not correctable by
   revert (already pushed; rewriting history is worse). Corrected by landing the
   good state on top, which `757df5b` does.
2. **It structurally defeats "no commit until tests pass."** An auto-committer on
   a timer commits whatever is on disk, red or green.
3. **`HEAD` moves without operator action.** Every "clean tree / green before
   commit" check in this and prior sessions implicitly assumed otherwise. The
   suite was therefore re-confirmed green *immediately* before `757df5b`, rather
   than relying on an earlier check.

**Auto-backup and verify-then-commit are both live and they conflict on history
legibility** (not on data safety — append-only, everything recoverable). The
distinguishing signal is the message prefix (`Auto-backup:` vs a real subject
line), which suffices only if a reader knows to look. **Candidate for an ADR.**
Deliberately not resolved in this task.

---

## 6. Live verification — evidence

### Rows before
```
('KPHX','PHX','2026-07-13','preliminary',108,82)
('KPHX','PHX','2026-07-14','summary',108,79)
('KPHX','PHX','2026-07-15','summary',107,81)
('KPHX','PHX','2026-07-15','preliminary',109,92)
TOTAL: 4
```

### Run 1 — all five stored, exit 0
```
phoenix: stored f59b81a0-... | climate_day 2026-07-16 | summary     | high=109 low=89
nyc:     stored b2ecf903-... | climate_day 2026-07-16 | summary     | high=95  low=75
chicago: stored 760e1bad-... | climate_day 2026-07-16 | summary     | high=95  low=76
miami:   stored aecfd08b-... | climate_day 2026-07-16 | summary     | high=94  low=80
austin:  stored ea2fdc88-... | climate_day 2026-07-16 | preliminary | high=79  low=73
EXIT CODE: 0
```

### Rows after run 1 — TOTAL 9
```
('KPHX','PHX','2026-07-16','summary',109,89)
('KNYC','NYC','2026-07-16','summary',95,75)
('KMDW','MDW','2026-07-16','summary',95,76)
('KMIA','MIA','2026-07-16','summary',94,80)
('KAUS','AUS','2026-07-16','preliminary',79,73)
DISTINCT STATIONS: ['KPHX','KNYC','KMDW','KMIA','KAUS']
```

**Station↔location pairs match the 2026-07-15 confirmed mapping exactly:**
KPHX/PHX, KNYC/NYC, KMDW/MDW, KMIA/MIA, KAUS/AUS. This is the silent-corruption
check, and it passes.

### Run 2 — all five skipped, exit 0, TOTAL still 9
```
phoenix: product f59b81a0-... already stored - skipped
nyc:     product b2ecf903-... already stored - skipped
chicago: product 760e1bad-... already stored - skipped
miami:   product aecfd08b-... already stored - skipped
austin:  product ea2fdc88-... already stored - skipped
EXIT CODE: 0
TOTAL: 9
```

### Wrapper verification — the decisive artifact

`cmd //c run_cli_collection.bat` → **exit 0**. The dated log shows before-and-after
in one view, same wrapper, same task:

```
[Thu 07/16/2026  0:30:02.30] CLI collection run starting (attempt 1)
phoenix: ... already stored - skipped                    <-- ONE city (old code)
[Thu 07/16/2026  0:30:04.58] SUCCESS on attempt 1 (exit 0)
============================================================
[Thu 07/16/2026 13:27:06.76] CLI collection run starting (attempt 1)
phoenix / nyc / chicago / miami / austin: all skipped     <-- FIVE cities (new code)
[Thu 07/16/2026 13:27:09.26] SUCCESS on attempt 1 (exit 0)
```

Row count still 9. No retry fired. **Wrapper and scheduler unchanged and proven
working — not asserted.**

---

## 7. Observations (E4, recorded not acted on)

1. **`report_kind` split by time zone.** This run (~13:30 ET) parsed
   phoenix/nyc/chicago/miami as `summary` and **austin as `preliminary`**.
   2026-07-15's samples, captured late afternoon local, were **all five
   preliminary**. Coherent explanation: NYC/CHI/MIA are past posting time and
   finalized; Austin is on CT and still preliminary. **This is more evidence for
   Open Item #6, not a resolution.** `parse_report_kind` keys on the literal
   string `VALID ... AS OF`; nothing yet proves that string means the same thing
   across all five issuing offices.
2. **Phoenix amendment behavior confirmed in the wild.** climate_day 2026-07-15
   now has two rows: `summary 107/81` and `preliminary 109/92`. Append-only
   amendment handling works on real data.
3. **Austin high = 79 at midday**, the second consecutive low-anomaly reading
   (07-15 was 78 observed vs 96 normal, departure −18). Plausible; worth watching.
4. **Phoenix stored rather than skipped on run 1** — a new product (`f59b81a0`)
   was issued after the 00:30 sweep's `5235bd24`. Expected behavior.

---

## 8. Open items carried forward

1. **NEW — ADR candidate: auto-backup vs. verify-then-commit.** See §5.3. The
   auto-backup task commits and pushes unverified intermediate states. Decide
   which discipline wins, or how they coexist legibly.
2. **Documentation correction (from 2026-07-15, still open):** the project state
   doc says the parser is "hardened to scope to the TODAY temperature block
   only." **It is not.** `parse_high_low` (lines 43–52) takes the *first* line
   starting with `MAXIMUM`; there is no block scoping. It works because
   `_first_int_after_label`'s regex captures `TEMPERATURE` from the normals line
   `MAXIMUM TEMPERATURE (F) 96`, which fails `re.fullmatch(r"-?\d+")` → returns
   None, and because the observed block precedes the normals block in every real
   product. **Do not change the parser** (Architect ruling: it passed 5/5 against
   real products). **Fix the documentation** — a future session reading "scoped
   to TODAY block" would believe a defense exists that does not.
3. **F3 / 11am ET delay rule** — still unencoded for Miami and Austin. Exact
   rulebook text still not captured. Sources:
   `.../product-certifications/MIAHIGH.pdf`, `.../AUSHIGH.pdf`.
   Does NOT gate collection.
4. **`report_kind` classification unverified** — see §7.1. Now has two days of
   contradictory-looking evidence with a plausible time-zone explanation.
5. **`settlement_sources` drift undetected** — Kalshi could re-point a market;
   nothing notices.
6. **README stale beyond the verification claims** — flagged in-file 2026-07-15.
7. **Manifest regeneration** — `scheduler/` and now `tests/test_collect_all.py`.
   Deferred under governance freeze.
8. **R5** — off-machine backup *with tested restore* for `data/` + `snapshots/`.
   Auto-backup covers the repo, not a tested restore.
9. **Ratification.** `757df5b` and this log are **E4**. Also still unratified:
   `0cf60e1`, `12f94c0`, the automation layer, the em-dash edit, the config
   cadence change.

---

## 9. Accrual status

**Before this session:** 1 city collecting (~30 city-days/month).
**After:** 5 cities collecting (~150 city-days/month).

V1 gate requires **≥300 gap-audited city-days over 3 months**. At five cities and
~150/month, that is reachable in ~2 months of wall clock. This task was the
binding constraint on that clock; it is now released.

First multi-city rows landed **2026-07-16**. That is the accrual start date for
NYC, Chicago, Miami, and Austin.

---

## 10. Definition of Done

| Requirement | Status | Evidence |
|---|---|---|
| One scheduled execution collects all five | ✅ | wrapper log 13:27, five cities |
| Failure isolation works | ✅ | 4 tests incl. ConfigError |
| Exit codes remain truthful | ✅ | exit 0 ×3 live runs; contract tested both directions |
| Full test suite passes | ✅ | 48 passed |
| Live verification passes | ✅ | 5 stored, correct station↔location pairs |
| Duplicate verification passes | ✅ | 5 skipped, 9 → 9 rows |
| Session log written | ✅ | this file |
| Changes committed | ✅ | `757df5b` |
| Changes pushed | ⬜ | pending |

---

## 11. Environment gotchas (cumulative — do not relearn)

- **`runpy.run_module` re-imports from source and discards monkeypatches.** A
  test doing this will silently hit the real network. (§5.1)
- **The repo is auto-committed and auto-pushed ~2×/day** by a Task Scheduler task
  outside the repo. `HEAD` moves without you. Re-confirm green immediately before
  committing. (§5.3)
- **Never use `/tmp` for anything Windows Python touches** — it resolves to
  `C:\tmp`, not Git Bash's `/tmp`. Use repo-root paths.
- **Never edit long files in Notepad** — it truncates silently. Use a Git Bash
  heredoc (`cat > file << 'EOF'`), which errors instead.
- **Use `write_bytes`, not `write_text`** — `write_text` translates `\n` → `\r\n`
  on Windows and produces a whole-file diff.
- **Disable the pager** for scripted output: `git -c core.pager=cat diff ...`
- **Do not paste expected-output or illustrative code back into bash.** `>` in a
  pasted line creates junk files; Python pasted into bash produces syntax errors.
- **A verification that errors is not a verification that passed.** Check that the
  check ran. (§5.2)
- **Em-dashes break console-encoded logs.** ASCII only in anything the `.bat`
  redirects.
- **Invalid NWS location IDs return HTTP 500, not 404.**
- **NWS requires a real contact email** in the User-Agent, or 403.
