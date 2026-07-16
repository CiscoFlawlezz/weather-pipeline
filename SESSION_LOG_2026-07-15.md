---
title: Session Log — 2026-07-15 — F2 Closure and M2 Expansion Discovery
status: E4 — AI-drafted testimony, pending Architect ratification (Invariant 3)
scope: weather-pipeline repo; discovery + governance correction only, no collector change
outcome: F2 CLOSED on primary source. Parser verified 5/5. Expansion NOT yet built.
next_step: Replace the Phoenix hardcode at collectors/nws_cli_collector.py:128 with
           config-driven iteration over all five cities.
---

# Session Log — 2026-07-15

**Intent at start:** expand Phoenix automation to NYC, Chicago, Miami, Austin.

**What actually happened:** the session never reached the expansion. Phase 0
discovery immediately surfaced that `cli_location_id` was unknown for four
cities (Open Item #3), and the Architect ruled that the F2 gate blocks
collection. F2 closure became the session. That was the correct call: F2 is
now closed on primary source, and the expansion is a clean, well-scoped next
task rather than work built on an open gate.

**Commits:** 2. Both pushed. `main == origin/main` verified.

---

## 1. Result in one paragraph

F2 is **closed against a machine-readable primary source**. Kalshi's
`GET /series/{ticker}` exposes a `settlement_sources` field naming the exact
NWS CLI product each contract settles on; its `issuedby` parameter is
identical to the NWS CLI `cli_location_id`. This corroborates the Architect's
direct read of each rules page on 2026-07-09. All four missing
`cli_location_id` values were discovered empirically, confirmed against the
product body, and committed. The existing parser was run against real captured
samples for all five cities: **5/5 pass, no code change needed.** The
expansion is therefore a **config-driven iteration change**, not a parser or
architecture change. Nothing about collection changed this session — no new
city is collecting yet.

---

## 2. Commits (weather-pipeline `main`, both pushed)

| SHA | Summary |
|---|---|
| `0cf60e1` | config: correct verified-flag warrant; add `cli_location_id` ×4 |
| `12f94c0` | docs: correct README station-verification claims; flag rest as stale |

Prior head was `fa4132a`. Push verified via `git status -sb` → `## main...origin/main`
(no ahead/behind). Suite green at **37 passed** before and after each commit.

A third commit (`test_connections.py`) was **planned and then dropped** — its
premise was void. See §6.

---

## 3. F2 closure — the evidence chain

### 3.1 The rulebook names were never rival series

The 2026-07-09 config comments cited `NHIGH`, `CHIHIGH`, `MIAHIGH`, `AUSHIGH`.
The config traded `KXHIGHNY`, `KXHIGHCHI`, `KXHIGHMIA`, `KXHIGHAUS`. Different
strings — which raised the possibility that the Architect had verified a
station for a series the lab would not trade.

**Resolved:** all four rulebook names return **404 as series tickers**. They are
the *contract-certification PDF filenames* exposed in each series' own
`contract_url`. `KXHIGHNY` → `NHIGH.pdf`. Same market, two names. The
Architect's read and the config always described the same contracts.

Consequence: the config's `# NOT confirmed via rules page` ticker comments
were **wrong**, and had been since 07-09.

### 3.2 Kalshi publishes the settlement source

`GET /series/{ticker}` → `settlement_sources[0].url`:

| City | Ticker | site | issuedby | Cert PDF |
|---|---|---|---|---|
| phoenix | `KXHIGHTPHX` | PSR | **PHX** | GLOBALTEMPERATURE.pdf |
| nyc | `KXHIGHNY` | OKX | **NYC** | NHIGH.pdf |
| chicago | `KXHIGHCHI` | LOT | **MDW** | CHIHIGH.pdf |
| miami | `KXHIGHMIA` | MFL | **MIA** | MIAHIGH.pdf |
| austin | `KXHIGHAUS` | EWX | **AUS** | AUSHIGH.pdf |

URL form: `https://forecast.weather.gov/product.php?site={site}&product=CLI&issuedby={issuedby}`

Chicago's source *name* is literally `"NWS Climatological Report Chicago Midway"` —
the exchange naming Midway, not O'Hare, in its own settlement declaration.

### 3.3 KEY IDENTITY (the session's most useful finding)

**Kalshi's `issuedby` == the NWS CLI `cli_location_id`.**

These were derived **independently**: `cli_location_id` was discovered by
probing `api.weather.gov` with candidate codes; Kalshi publishes `issuedby`
as its settlement source. They match for all five cities. Five-way agreement
across: Kalshi settlement_sources → cli_location_id → NWS product body →
config `station_id` → Architect's 07-09 rules-page read.

This means F2 for any *future* city is a single API call, not a manual read.

### 3.4 Confirmed mappings (primary-source empirical, 2026-07-15)

| City | `cli_location_id` | AWIPS | Office | Product body says | Config `station_id` |
|---|---|---|---|---|---|
| phoenix | `PHX` | CLIPHX | KPSR | PHOENIX AZ | KPHX |
| nyc | `NYC` | CLINYC | KOKX | THE CENTRAL PARK NY CLIMATE SUMMARY | KNYC |
| chicago | `MDW` | CLIMDW | KLOT | THE CHICAGO-MIDWAY CLIMATE SUMMARY | KMDW |
| miami | `MIA` | CLIMIA | KMFL | THE MIAMI CLIMATE SUMMARY | KMIA |
| austin | `AUS` | CLIAUS | KEWX | THE AUSTIN BERGSTROM CLIMATE SUMMARY | KAUS |

The naive pattern (`station_id` minus leading `K`) holds for all five — but it
is **earned by test, not assumed**. It was explicitly distrusted until the
product bodies confirmed it.

### 3.5 Aliases are NOT aliases — distinct products, proven by hash

Multiple location IDs per office return HTTP 200. They are **different
products** with **different sha256 bodies**:

```
nyc:     NYC=4aa5a886(Central Park)  LGA=4b8ad4ef(LaGuardia)  JFK=ae1d66ef(Kennedy)
chicago: MDW=25203652(Midway)        ORD=01f31e3c(O'Hare)     LOT=4f17abac(Romeoville WFO)
miami:   MIA=a126090e(Miami)         FLL=de1b31a2(Fort Lauderdale)
austin:  AUS=f30f616e(Bergstrom)     ATT=fc2803ee(Camp Mabry)
```

**TRAP AVOIDED:** `LOT` is the **Romeoville WFO**, not Chicago. A
one-candidate-per-office probe (the original plan) would have sampled
Romeoville for Chicago.

**API behavior note:** invalid location IDs return **HTTP 500**, not 404. Do
not read a 500 as "this ID does not exist."

---

## 4. Parser verification — 5/5, no change needed

The existing `parse_high_low` / `parse_report_kind` were run against real
captured samples for all five cities:

```
phoenix PHX  PASS  (109, 92)   kind='preliminary'
nyc     NYC  PASS  (95, 78)    kind='preliminary'
chicago MDW  PASS  (95, 76)    kind='preliminary'
miami   MIA  PASS  (93, 80)    kind='preliminary'
austin  AUS  PASS  (78, 72)    kind='preliminary'
5/5 passed
```

**Format variance found and survived:** Phoenix and NYC time tokens have **no
colon** (`407 PM`); Chicago, Miami, and Austin **do** (`2:38 PM`). The parser
is indifferent. This was unknown before the samples were captured — Phoenix
alone never produced a colon.

**The tomorrow-normals trap is present in all five products.** The existing
defense (require a numeric token immediately after a *bare* `MAXIMUM` label;
the normals lines read `MAXIMUM TEMPERATURE (F)`) held in every case.

**Austin was the live danger case:** observed max **78**, normal **96**,
departure **−18**. A normals-grabbing parser returns 96 — plausible for Austin
in July, no exception, no red test, silently wrong. It returned 78.

Samples live at `C:\tmp\discovery\samples\sample_cli_*.txt` (throwaway,
uncommitted; `.gitignore` already covers `sample_cli_*.txt`).

---

## 5. What changed in the repo

### `0cf60e1` — config.yaml
- Added `cli_location_id` for nyc (`NYC`), chicago (`MDW`), miami (`MIA`),
  austin (`AUS`). Phoenix already had `PHX`.
- Rewrote all verification comments to carry the **warrant**, not just the claim.
- `verified: true` values **unchanged** ×5 — the flag was always going to end up
  `true`; what was wrong was its *warrant*, and a boolean cannot record warrant.
  The comments now do.
- Header block rewritten: documents the two independent primary sources, the
  `issuedby == cli_location_id` identity, and that `verified` is a human-facing
  annotation no code reads.
- Em-dashes replaced with `--` throughout, per the `f1eeeb9` precedent.
- Recorded the unencoded 11am ET rule inline for miami and austin.

**Verification method that matters:** the diff was checked by parsing both
versions to sorted JSON and diffing the *data*, ignoring comments entirely:

```bash
git show HEAD~1:config.yaml > before.yaml
venv/Scripts/python.exe -c "import yaml,json; print(json.dumps(yaml.safe_load(open('before.yaml')), sort_keys=True, indent=1))" > before.json
venv/Scripts/python.exe -c "import yaml,json; print(json.dumps(yaml.safe_load(open('config.yaml')), sort_keys=True, indent=1))" > after.json
diff before.json after.json
```

Result: **exactly four additions** (the four `cli_location_id` keys), nothing
else. Reusable — this is the right way to verify a comment-heavy config edit.

### `12f94c0` — README.md
- `Station IDs unverified` → **VERIFIED (2026-07-15)** with the full warrant.
- Clarified that *series existence* ≠ *rules-page station check* — two different
  claims that share the word "verified" (see §6.2).
- Structure line now mentions `cli_location_ids`.
- **Appended an explicit staleness notice.** The README still describes
  Milestone 1a: the title, the "no storage, no scheduling yet" scope line, the
  "has not run against the live APIs yet" limitation, the project tree, and the
  "Milestone 1b (next)" section are all stale. **Deliberately not fixed** —
  out of scope for a verification-warrant change. Flagged rather than silently
  left, and flagged rather than opportunistically rewritten.

---

## 6. Corrections — assertions I made that were WRONG

Recorded per KT Rank 5. Every one was caught by the instrument, not by me.

### 6.1 "The aliases are the same product" — WRONG
Phase 0 showed identical header lines (`CDUS41 KOKX 152033`) across NYC/LGA/JFK.
I concluded one product served all three, and raised an alarm about
Midway/O'Hare contamination.

The header is the **WMO heading** — office + issuance timestamp. KOKX transmits
all its station CLIs in the same minute, so headings match while products
differ. The discriminator is the **AWIPS id on the next line** (`CLINYC` vs
`CLILGA`). **The sha256 hash disproved me.** Alarm withdrawn.

### 6.2 "test_connections.py:147 manufactured the flag bug" — WRONG
I asserted from a grep hit that line 147 told the user to flip `verified: true`
after a series-*existence* test. The actual text (lines 146–148):

> `"Next: verify station IDs against each market's rules page, flip 'verified: true' in config.yaml, then build 1b"`

The instruction was **correct and always had been** — it explicitly requires
the rules-page check *first*. **Commit 2's premise was void and the commit was
dropped. No code change was warranted.**

Probable real cause of the premature flip: a **naming collision**. Lines 63–79
use a local `verified_series` list meaning "series that exist per API" — same
word, different claim, adjacent code. Not a defect.

### 6.3 "The YAML comment indentation broke the parse" — WRONG
YAML comments cannot break parsing at any indentation. I diagnosed from a
truncated pytest dump and asserted twice.

### 6.4 "`miami` is at the config root" — WRONG
I misread pytest's truncated `mapping=` output, which was showing a *nested*
dict. `cities` was intact with all five. Only `collection` was actually missing.

**The real cause of both:** Notepad silently truncated a long paste, dropping
the value from `station_id:` on austin's line 79 and consuming everything
below it — including the whole `collection:` block. Fixed by writing the file
via a Git Bash heredoc, which errors rather than truncating.

### 6.5 The `/tmp` path trap — WRONG THREE TIMES
Windows Python does **not** resolve Git Bash's `/tmp`. `pathlib.Path("/tmp/x")`
resolves to `C:\tmp\x` (drive-relative), while Git Bash's `/tmp` is
`C:\Users\rjkir\AppData\Local\Temp`. This cost three steps:

1. Discovery samples appeared "lost" — they were at `C:\tmp\discovery\samples`.
2. A `sys.path.insert(0, "/c/Projects/weather-pipeline")` failed to import.
3. **The config value-diff check silently did not run.** `git show HEAD:config.yaml > /tmp/before.yaml`
   (Git Bash `/tmp`) then Python reading `/tmp/before.yaml` (`C:\tmp\`) →
   `FileNotFoundError`, empty `before.json`, and a `diff` output of `0a1,60`
   that **looked like success** (a wall of `>` lines) but compared nothing
   against everything. **A commit landed on a check that never ran.** It was
   re-verified afterward and was correct — but that was luck, not process.

**Rule going forward:** never use `/tmp` for anything Python touches. Use repo-root
paths that both Git Bash and Windows Python agree on. And a `diff` that reports
"everything is new" is a **failed check**, not a passed one.

### 6.6 The CRLF churn
Python's `write_text` on Windows translated `\n` → `\r\n`, making git report
the entire README as changed (99 insertions / 79 deletions). Content was
correct — `git diff --ignore-all-space` proved it. Fixed with `write_bytes`,
which bypasses text-mode translation. Final diff: 29/9.

### 6.7 The pattern
**Every wrong assertion came from reasoning off a pointer (a grep hit, a
truncated dump, a shared prefix, a print statement) instead of the artifact.**
This is the same failure mode as parsing against a guessed format — F1 applied
to code and config rather than to a data feed. The instrument caught all of it:
a hash, a test suite, `ConfigError`, and reading the actual line. That is the
governance framework working. But the operator (me) repeatedly needed it to.

**Governance note candidate:** F1 discipline should be stated to cover *any*
artifact — rulebooks, config, source lines — not only data formats. "Capture
the real sample first" generalizes to "read the actual thing before asserting
what it says."

---

## 7. Open items carried forward

1. **F2 — CLOSED** (was Open Item #2). Closed on primary source 2026-07-15.
2. **Per-city `cli_location_id` — CLOSED** (was Open Item #3). All five in config.
3. **THE OBJECTIVE IS NOT DONE.** No city other than Phoenix collects. See §8.
4. **F3 / 11am ET delay rule (Open Item #4)** — still unencoded for Miami and
   Austin. Architect read it on 07-09; the **exact rulebook text has not been
   captured**. Primary sources are now known and public:
   - `https://kalshi-public-docs.s3.us-east-1.amazonaws.com/regulatory/product-certifications/MIAHIGH.pdf`
   - `https://kalshi-public-docs.s3.us-east-1.amazonaws.com/regulatory/product-certifications/AUSHIGH.pdf`

   **Does NOT gate collection** — CLI rows are facts about stations; the delay
   rule governs which row *settles a contract* (a mapping question, downstream).
   **Deliberately not fixed this session:** the rule's meaning is unknown
   (does it shift the settlement day? invalidate pre-11am amendments? select a
   specific issuance?). Each implies a different change, and one of them would
   touch `core/climate_day.py` — the settlement-day authority, 12 tests deep and
   load-bearing. **Read the PDFs before touching anything.** F1.
5. **NEW: `settlement_sources` drift is undetected.** Kalshi could re-point a
   market and nothing in the pipeline would notice. Candidate for a future
   collector (a new task under one-task-per-session, not a patch).
6. **`report_kind` observation (unverified)** — a post-midnight live run
   classified `summary`, not `preliminary`. Note: all five samples captured
   this session (late afternoon / evening local) parsed as `preliminary`,
   consistent with the summary branch being a post-midnight phenomenon. Still
   unverified against real CLI posting/amendment times.
7. **`config.yaml` cadence note is stale** — still says sweep times are
   "reasoned defaults, NOT verified against observed CLI posting times." True,
   and now more tractable: real issuance times were observed this session
   (PHX 00:21Z, NYC 20:33Z, CHI 21:32Z, MIA 20:24Z, AUS 22:44Z).
8. **README is stale beyond the verification claims** — flagged in-file. Separate task.
9. **Manifest regeneration** for `scheduler/` — deferred under governance freeze.
10. **R5** — off-machine backup with tested restore for `data/` + `snapshots/`.
    Still open. Both repos are pushed; that is not the same as a tested restore.
11. **Ratification.** Everything this session is **E4**. `0cf60e1`, `12f94c0`,
    and this log are all pending Architect ratification.

---

## 8. Next session — scope (read this first)

**One task: replace the Phoenix hardcode with config-driven iteration.**

### The starting point, read from the actual file (not inferred)

`collectors/nws_cli_collector.py`:
- **Line 79:** `def collect_city(city: str, db_path: str) -> str:` — **already
  takes a city argument.** Returns a status string.
- **Line 123:** `if __name__ == "__main__":`
- **Line 126:** `db = sys.argv[1] if len(sys.argv) > 1 else "data/pipeline.db"`
- **Line 128:** `print(collect_city("phoenix", db))` ← **the entire hardcode**

`collect_city` internally resolves `station`, `location_id`, and `climate_day(city, ts)`
from config per city, and appends one row per distinct `product_id`.

### What this implies

- **The change is small.** Config already has all five `cli_location_id` values.
  The parser already passes 5/5. `collect_city` already parameterizes on city.
- **The wrapper is already city-agnostic.** `run_cli_collection.bat` calls
  `python -m collectors.nws_cli_collector "%DB%"` and knows nothing about
  Phoenix. Its header *comment* says "Phoenix collector" — a comment, not logic.
- **The scheduler XMLs are almost certainly untouched.** They invoke the wrapper.
  A single multi-city sweep per time slot needs no new tasks. **Verify, don't assume.**

### The one real design decision

**Failure isolation.** Today a single `collect_city` call either succeeds or
raises, and the wrapper's non-zero exit is meaningful. With five cities, a naive
loop lets one city's network blip abort the other four — **losing four
city-days of non-backfillable accrual to one transient error.**

Requirement: **each city must be attempted independently**, and the process must
still **exit non-zero if any city failed**, so Task Scheduler never records a
false success. Those two requirements are in tension and the resolution must be
explicit and tested. This is the substance of the task; the loop itself is trivial.

### Preserve every existing guarantee

Append-only. Idempotent by `product_id`. Non-zero exit on failure. Dated
automation log. **Phoenix's behavior must be provably unchanged.**

### Sequence

1. Confirm clean tree, suite green at 37, `main == origin/main`.
2. Read lines 120–128 of the collector before editing. (Do not skip. See §6.2.)
3. Decide and state the failure-isolation semantics **before** writing code.
4. Write the loop + a test that proves per-city failure isolation and the
   non-zero aggregate exit. **Test first or alongside — not after.**
5. Full suite green **before** commit. (`0ab970e` lesson.)
6. Live run: verify all five store rows, then re-run and verify all five skip
   as duplicates.
7. Verify the wrapper still logs, retries, and exits non-zero.
8. Commit. Push. One task, done.

**Accrual note:** four cities × ~1 city-day/day of non-backfillable data are
currently not being collected. The V1 gate needs ≥300 gap-audited city-days over
3 months. This task is the binding constraint on that clock.

---

## 9. Environment gotchas (hard-won, do not relearn)

- **Never use `/tmp` for anything Windows Python touches.** Use repo-root paths.
- **Never edit long files in Notepad.** It truncates silently. Use a Git Bash
  heredoc (`cat > file << 'EOF'`), which errors instead.
- **Use `write_bytes`, not `write_text`,** when line endings matter.
- **Disable the pager** for scripted output: `git -c core.pager=cat diff ...`
- **Do not paste expected-output text back into bash.** `>` in a pasted line
  creates junk files. (Happened twice: `cli_location_id:` and a stray heredoc.)
- **Em-dashes break console-encoded logs.** ASCII only in anything the `.bat`
  redirects. (`f1eeeb9`.)
- **Invalid NWS location IDs return HTTP 500, not 404.**
- **NWS requires a real contact email** in the User-Agent, or 403.
- **Verify a file was written with `ls`.** A print statement saying `saved=...`
  is an intention, not a result. (§6.5.)
