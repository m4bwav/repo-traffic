---
title: Modernization and v1 release
kind: plan
status: active
date: 2026-10-08
verified: 2026-10-08
stale_after: never
tags: [v1, plan, pypi, github-actions, tests, release, wiki]
summary: "the living plan for repo-traffic 1.0.0: survey, what 9b6e754 gets wrong, decisions D1-D18 with exceptions E1-E5, test strategy, phases 0-8 with checkboxes, size budget, images, wiki, verification"
---

# Modernization and v1.0.0 release plan: repo-traffic

The first package-modernize run on a Python command-line tool, and the first command-line wiki of wikiwright. The reference is the frozen source of 9b6e754, recorded in `tests/golden/` (Phase 0). Evidence goes to [../log.md](../log.md); the survey is [../notes/2026-10-08-survey.md](../notes/2026-10-08-survey.md).

## Status

Active. Phase 2 (rewrite) from 2026-10-08. Ruling on 2026-10-08, quoted: "I'll try to setup pypi account, do everything else that you can": D3 yes (PyPI; the maintainer sets up the account and the pending publisher), every other recommendation stands, so D10's repos.csv and PyPI downloads are in (E6).

## Goal

- A tested, linted, size-gated repo-traffic 1.0.0 that runs on Windows, macOS and Linux from Python 3.9 on, with the standard library only.
- Every recorded behaviour of 9b6e754 kept byte for byte, except the named fixes E1 to E5.
- The live scheduled task and the existing `data/` keep working with no re-registration.
- Released through a gated workflow with attested artifacts (and PyPI, if D3 is ruled yes); README images and a wiki that a stranger can follow on any OS.

## Where it stands (survey 2026-10-08)

| Fact | Value | Evidence |
|---|---|---|
| Published | nothing; PyPI name `repo-traffic` free | pypi.org JSON 404 |
| Source, tests | 253 lines, one file, stdlib + gh; no tests, no CI | survey note |
| Repository | public, MIT, 2 commits, no rulesets, no workflows, Dependabot off, secret scanning on | notes/2026-10-08-survey-github.txt |
| Golden capture | 18 cases, Windows and Linux, deterministic; replays on 3.9 and 3.12 | `tests/golden/`, log |
| Dead services, leaked credentials, images | none, none, none | survey |
| Wiki | placeholder Home.md only (d6a39f0) | `git ls-remote` |

## What 9b6e754 gets wrong, confirmed, and what v1 does

1. No push access is silent (`no-push-access`): fixed by E3.
2. One failing source fails the whole run before `daily.csv` is merged (`npm-empty-body`, `npm-429-every-time`, `npm-search-404`, `nuget-replica-503`, `nuget-replica-unreachable`): fixed by E2.
3. `--help` runs a full snapshot, `--top` with no value is an IndexError, unknown flags are ignored: fixed by E1.
4. A failure before the data folder is known logs to the default folder: fixed by E4.
5. An older `downloads.csv` header gets misaligned rows: fixed by E5.
6. Ties keep API order: fixed with no recorded change (name as the last sort key; every recorded tie already falls in name order).
7. Nothing reports a missed run: v1 adds a gap warning (D7).

## Decisions (recommendation first; silence means the recommendation stands)

| # | Question | Recommendation | Why | Alternative |
|---|---|---|---|---|
| D1 | Compatibility promise | Every recorded case byte for byte on its OS (Windows recording on Windows, posix on macOS and Linux), except E1 to E5 below, listed in one exceptions file the golden test reads | The live `data/` and the task depend on exact files | Compare parsed data instead of bytes (weaker; hides line-ending and order changes) |
| D2 | Layout | Stay one file, `repo_traffic.py` at the root, packaged as a single module (`py-modules`) with a `repo-traffic` console command. Run as a file it keeps reading `repo_traffic.json` and `data/` next to itself; run as the command it uses the current folder; a new `--config PATH` overrides both | The task's path stays valid, AGENTS.md's one-file rule holds, the harness runs it unchanged, it fits the budget | `src/repo_traffic/` package: cleaner tests, but the entry moves, the task needs re-registering, and more files for a 500-line tool |
| D3 | Distribution | PyPI too, through Trusted Publishing from release.yml in a `pypi` environment with you as required reviewer; rehearse with `1.0.0b1` on real PyPI (installers skip prereleases) instead of TestPyPI. Your steps: a PyPI account with 2FA and a pending publisher (owner m4bwav, repository repo-traffic, workflow release.yml, environment pypi). GitHub Release with wheel, sdist, SHA256SUMS and attestations either way | `pipx install repo-traffic` is how strangers install a Python CLI; the name is free; it proves the skill's untested pypi.md | GitHub only (`pipx install git+https://github.com/m4bwav/repo-traffic@v1.0.0`): no account work; PyPI can follow in 1.0.1 |
| D4 | Python floor and CI matrix | Keep `>=3.9`. CI: 3.9 and 3.14 on ubuntu, windows and macos; 3.10 to 3.13 on ubuntu; 3.15 when it ships | macOS's own `/usr/bin/python3` is 3.9, a real audience for a cron job; the capture proves 3.9 works; it costs two CI rows | `>=3.11` (oldest line still supported, 3.10 ended 2026-10-01): drops macOS system Python users |
| D5 | Runtime dependencies | None (standard library + gh). Dev only, pinned in requirements-dev.txt: pytest, coverage, ruff, build, twine; Dependabot pip and actions with a three-day cooldown | Zero install cost; matches the README | uv with a lockfile: faster, but one more tool for contributors |
| D6 | Names | Keep every flag and config key. Add `--help` and `--version` (argparse), `--config PATH`. Nothing else | Each fixes a captured bug or a D2 need | A `status` subcommand (left for later) |
| D7 | Errors, exit codes, missed runs | Exit 0 ok; 1 when any source failed (run.log line `partial` naming each failed source, or `FAILED` when nothing was saved); 2 for bad arguments. A run whose previous `ok` line in run.log is more than 14 days old writes `gap: N days since the last complete run, traffic before YYYY-MM-DD is lost` to run.log and the top of summary.md | The task's Last Run Result shows failure; the gap is the one loss the tool exists to prevent | A notification (email, toast): needs services or OS code |
| D8 | Scheduling | Keep `install-task.ps1` as it is. Document cron, a systemd user timer and a launchd agent (README short form, wiki Scheduling page with tested files). No `--install-schedule` | Three OS-specific installers in code would double the script; recipes are short | `--install-schedule` for all three OSes (about 150 lines and three untestable-in-CI paths) |
| D9 | Output formats and CSV versions | All files unchanged. A header is its version: columns are only ever added at the end; a known older header is migrated once in place, keeping downloads.csv.bak (E5); an unknown header stops the CSV write with an error naming the file and writes the rest | Your live `data/` keeps working; no silent misalignment | Version files (`downloads.v2.csv`): splits history |
| D10 | New data sources | repos.csv: one row per repository per run with stars, forks and release downloads (already fetched; about 15 lines). PyPI downloads from pypistats.org for packages named in `pypi_packages` (PyPI has no API listing a user's projects; about 30 lines), only if D3 is yes. Not GitHub Pages (no traffic API exists), not dependents (no API: GitHub's "Used by" is HTML only, libraries.io needs a key). Not a trend report yet (needs a few runs of data) | Stars and forks have no history anywhere else; PyPI only matters once something is published there | All or none of them |
| D11 | Size budget | Script lines: green up to 600, yellow 601 to 800 (CI warns), red over 800 (CI fails). Wheel: green up to 25 KB, yellow to 40 KB, red over 40 KB. Runtime dependencies: any is red. Checked by scripts/check_size.py in CI | Today 253 lines; v1 estimate about 450 | Tighter (500 lines): pushes features out |
| D12 | Tests | pytest. Unit tests for every function (the module imported, gh and HTTP faked in process); the golden test (harness against the root script, both recordings' cases on their OS, exceptions file); the frozen original replayed on every CI OS (`capture.py --check`); Windows path cases; coverage at least 90 percent of lines | Everything the harness records, plus the branches it cannot reach cheaply | unittest only (no dev dependency, more boilerplate) |
| D13 | Workflows | ci.yml (ruff check and format, size gate, matrix tests, build, `twine check --strict`, install the wheel in a fresh venv and run `repo-traffic --version` and the golden test against the installed module); release.yml on a `v*` tag (build once, attest, GitHub Release in a `release` environment with you as reviewer, PyPI job in `pypi`); actions pinned to SHAs; actionlint and zizmor clean | The skill's defaults for a gated release without a registry stage | Release by hand from this PC (against the skill's rules) |
| D14 | Version and tags | 1.0.0 (rehearsal 1.0.0b1, tag `v1.0.0b1`). Tag 9b6e754 as `v0.1.0` (tag only, no Release) so the CHANGELOG has a base | First release; PEP 440 version forms | 0.2.0 (signals unstable when it is not) |
| D15 | Repository settings | Topics (github-traffic, traffic, downloads, npm, nuget, pypi, cli, python); homepage the PyPI page (D3 yes) or the wiki; ruleset on master (no deletion, no force push, required check `ci`, admin bypass); tag ruleset admins only; Dependabot alerts and security updates on; SECURITY.md from the skill's tool template | The skill's Phase 4 set | none |
| D16 | Images | A banner from comfyui-gen on the Mac (up on 2026-10-08, ComfyUI 0.38.2), plus a chart of `daily.csv` made from the invented fixture data with chartwright (PNG); both under docs/images/, under 400 KB together, alt text, linked by raw URLs pinned to the tag; excluded from the sdist | Shows what it does without a real repository name | Chart only |
| D17 | Wiki | wikiwright, headless, the page set: Home, Getting started, Commands and options, Output files, Scheduling, Data sources and limits, FAQ, Development, with sidebar and footer; every example run against the release with the fixture stand-ins | The kickoff's set; examples never touch your accounts | Fewer pages |
| D18 | Your PC after the release | No re-registration needed (D2 keeps the path). Pull the clone to the tag, run the task once from Task Scheduler, check run.log says ok and `daily.csv` gained rows | D2 | Install with pipx and point the task at `repo-traffic` |

Exceptions to the recording (E1 to E5), one entry each in tests/golden/exceptions.json:

| # | Case(s) | Old | New |
|---|---|---|---|
| E1 | `help-flag-runs-a-snapshot`, `top-without-value` | `--help` runs a snapshot; `--top` alone raises IndexError | usage on stdout, exit 0, nothing fetched; `--top` alone: usage error on stderr, exit 2, nothing written |
| E2 | `npm-empty-body`, `npm-429-every-time`, `npm-search-404`, `nuget-replica-503`, `nuget-replica-unreachable` | whole run FAILED after github.json, no CSVs | an empty body is retried like a 429; a source that still fails is left out, everything else is saved and merged, run.log says `partial` with the failed source, exit 1; one NuGet replica down: the other is used, no failure |
| E3 | `no-push-access` | `null` traffic, summary shows 0, nothing said | same data, plus `traffic_error` in that repository's github.json entry, a "No traffic access" line in summary.md and stdout, and the count in run.log |
| E4 | `gh-login-fails-logs-to-default-data` | FAILED logged in `data/` next to the script | logged in the `--data` folder |
| E5 | `downloads-csv-old-header` | 7-column rows under a 6-column header | file migrated to the current header once, downloads.csv.bak kept, rows appended |

Added outputs that change every recorded case get one more entry: if D10's repos.csv is ruled yes, every successful case gains that file (E6), and D7's gap line appears only in `second-run-merges-daily` if ever (13 days: no gap line, so no change).

## Build and package specifics

pyproject.toml with PEP 621 metadata, hatchling (at least 1.26) as the backend, `py-modules`-style single module, `requires-python >=3.9`, `license = "MIT"` with `license-files`, `[project.scripts] repo-traffic = "repo_traffic:cli"`, version read from `__version__`. The sdist and wheel carry `repo_traffic.py`, LICENSE and README only.

## Phases

### Phase 0: survey and baseline (2026-10-08)
- [x] Survey in ai-docs/notes; repository facts; PyPI name free
- [x] Golden capture of 9b6e754: tests/golden/, 18 cases, Windows and Linux, deterministic, replays on 3.9 and 3.12 (commit 896876d)
- [x] everlast (mode repo, sync push); AGENTS.md block; Copilot pointer
### Phase 1: plan
- [x] This plan. Ruled 2026-10-08 (Status). **Stop**: the maintainer rules on D1 to D18 and E1 to E5
### Phase 2: rewrite on branch v1
- [ ] Golden test first, green against the rewrite with the exceptions file; canary red, reverted, green; recording untouched since 896876d
- [ ] Unit tests, coverage, ruff, size gate; pyproject; workflows and Dependabot from the templates; lint-workflows clean
- [ ] README (install per OS, usage, limits), CHANGELOG, SECURITY.md, AGENTS.md
- [ ] Pushed, pull request with a "For review" list
### Phase 3: review
- [ ] Independent read-only review; findings fixed with tests; summary on the pull request
### Phase 4: CI, settings, merge
- [ ] CI green on all rows; rulesets and settings (D15); merge; tag v0.1.0 on 9b6e754
### Phase 5 and 6: rehearsal and release
- [ ] 1.0.0b1 tagged, gated, approved, verified (GitHub Release assets, attestations; PyPI if D3)
- [ ] 1.0.0 the same; CHANGELOG dated
### Phase 7: images and wiki
- [ ] Banner and chart in the README; wiki written, pushed, `wikiwright.py live` clean
### Phase 8: wrap-up
- [ ] The task run once on the maintainer's PC (run.log ok, daily.csv grew); HANDOFF, log, decision record; skill lessons and pull requests; inventory row; next kickoff prompt

## Test strategy

| Layer | What it proves | How | Runs where |
|---|---|---|---|
| Golden | old behaviour kept, except E1-E5 | harness on the root script and on the installed module | 3 OSes, 3.9 and 3.14 |
| Recording still true | the recording describes the original on this OS | `capture.py --check` | 3 OSes |
| Unit | every function, every branch the harness cannot reach cheaply | pytest, in-process fakes | full matrix |
| Package | the wheel installs and runs | fresh venv, `repo-traffic --version`, golden on it | 3 OSes |
| Size | budget | scripts/check_size.py | ubuntu |

## Security

No tokens: gh holds the user's login; the tool reads only. Nothing it writes leaves the data folder. Workflows: `contents: read` by default, id-token set to write only in the publish and attest jobs, actions pinned to SHAs, `persist-credentials: false`, tag ruleset admins only. PyPI through Trusted Publishing only, gated by the `pypi` environment. The README says what it does not do (no data leaves your machine except the API calls, no telemetry).

## Verification checklist

| Claim | Command or place | Expected |
|---|---|---|
| Golden kept | `pytest tests/test_golden.py` | pass on every CI row |
| Recording untouched | `git diff --exit-code 896876d -- tests/golden/original tests/golden/recording-*.json tests/golden/cases.py tests/golden/harness.py tests/golden/shim.py tests/golden/fakegh.py tests/golden/capture.py` | empty |
| Size | `python scripts/check_size.py` | green |
| Release | GitHub Release v1.0.0 with wheel, sdist, SHA256SUMS; `gh attestation verify` | verified |
| PyPI (if D3) | `pipx install repo-traffic==1.0.0` in a fresh shell; `repo-traffic --version` | 1.0.0 |
| Task | Task Scheduler run, then run.log last line and daily.csv row count | ok, more rows |

## Risks and open points

- nuget.org's stats report is undocumented and could change shape; v1 treats a missing or odd report as "no 6-week figure", never as a failure.
- GitHub's traffic API counts the tool's own CI clones; nothing to do but say so.

## Next single action

The maintainer rules on the table; then Phase 2.
