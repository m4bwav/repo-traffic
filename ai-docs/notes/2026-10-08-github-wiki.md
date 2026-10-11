---
title: GitHub wiki written for 1.0.0b1
kind: note
date: 2026-10-08
verified: 2026-10-08
stale_after: 2027-04-08
tags: [wiki, docs, 1.0.0b1, github]
summary: "the wiki's eight pages, where their git working copy is, how every example was verified against repo-traffic 1.0.0b1 from PyPI through the golden harness, the facts found on the way, the inaccuracies in the shipped README and CHANGELOG, and how to update the wiki; read before touching the wiki or the README sentences listed under inaccuracies"
---

# GitHub wiki for 1.0.0b1

## Summary

The maintainer asked for the wiki through the wikiwright skill (Steps 1 to 6 and 8; Step 7, publishing, left to the maintainer's session). Eight pages plus a sidebar and footer were written from the README, CHANGELOG, AGENTS.md, the plan, `repo_traffic.py`, `install-task.ps1`, the tests and the workflows. Every example was produced by `2026-10-08-wiki-verify.py` (next to this note) against repo-traffic 1.0.0b1 installed from PyPI, on Windows and Linux, with the golden harness standing in for GitHub, npm, NuGet and pypistats.org. Not committed and not pushed: the pages sit uncommitted in the wiki working copy, and these notes uncommitted in this clone.

Pages: Home, Getting-Started, Commands-And-Options, Output-Files, Scheduling, Data-Sources-And-Limits, FAQ, Development, plus `_Sidebar.md` and `_Footer.md`.

## Where the pages are

`D:\m4bwa\Claude\Projects\Ai\repo-traffic.wiki` (a sibling of this clone, outside this repository), branch `master`, remote `origin` = `https://github.com/m4bwav/repo-traffic.wiki.git`. Files: `Home.md` (over GitHub's placeholder), `Getting-Started.md`, `Commands-And-Options.md`, `Output-Files.md`, `Scheduling.md`, `Data-Sources-And-Limits.md`, `FAQ.md`, `Development.md`, `_Sidebar.md`, `_Footer.md`. Plain markdown links between pages (`[Scheduling](Scheduling)`), no wikilinks, LF line endings (0 CR bytes, checked with node).

## How it was published

Preflight (2026-10-08): `STATE: placeholder` (one commit, d6a39f0 "Initial Home page"), so a plain commit and `git push` will fast-forward. Not done: the run was told not to commit or push. Whoever publishes commits in the wiki working copy (message naming 1.0.0b1 and the pages), runs `git push`, then `python <wikiwright>/scripts/wikiwright.py live m4bwav/repo-traffic D:\m4bwa\Claude\Projects\Ai\repo-traffic.wiki` and writes its line here.

## Updating the wiki later

1. `git -C D:\m4bwa\Claude\Projects\Ai\repo-traffic.wiki pull --ff-only`, then edit the pages. Page names are the file names with hyphens; links are `[Text](Page-Name)`.
2. Re-verify: bump `VERSION` in `2026-10-08-wiki-verify.py` (next to this note) and run it from a scratch folder outside the repository. Windows: `WIKI_VERIFY_TASKS=1 WIKI_VERIFY_PIPX=1 python ai-docs/notes/2026-10-08-wiki-verify.py --out <scratch>/wiki-verify.out.txt` (it finds the clone two folders up, creates a fresh venv in `%TEMP%\repo-traffic-wiki-verify` and installs `repo-traffic==VERSION` from PyPI; `WIKI_VERIFY_SOURCE` takes a wheel path instead). Linux (WSL here has no `ensurepip`): install the version into a venv with uv, then `WIKI_VERIFY_PYTHON=<venv>/bin/python python3 ai-docs/notes/2026-10-08-wiki-verify.py --out <scratch>/wiki-verify.linux.out.txt`. Then `python <wikiwright>/scripts/wikiwright.py diffout 2026-10-08-wiki-verify.out.txt <new output>` and the same for the Linux pair: every difference is a page to fix (exit 1 means differences). `diffout ... --save` saves the new output over the old.
3. Checks: `wikiwright.py outputs <wiki dir> <new Windows output> <new Linux output>`, `wikiwright.py snippets <wiki dir> 2026-10-08-wiki-verify.py`, `python 2026-10-08-wiki-verify.py --check-pages <wiki dir> --out <new Windows output>` (the command-line blocks `snippets` does not read), `wikiwright.py check <wiki dir> --version <new>`, and everwrite's `tells.py --wiki <wiki dir>/*.md`.
4. Commit, `git push`, then `wikiwright.py live`. When a release changes the version, the pages that name it are: `_Footer.md` (version and date), `Home.md` (the version paragraph and "the only version on PyPI"), `Getting-Started.md` (pipx and `--version` transcripts, the prerelease paragraph), `Commands-And-Options.md` (`--version` transcript), `FAQ.md` ("Does pip install the beta?"), `Development.md` (594 lines, the wheel size, the release paragraph, the test counts). At 1.0.0, rewrite the prerelease sentences on Home, Getting-Started and FAQ.

## How the examples were verified

`2026-10-08-wiki-verify.py` installed `repo-traffic==1.0.0b1` from PyPI (uploaded 2026-10-09 03:24 UTC) into a fresh venv and confirmed the installed `repo_traffic.py` equals the tag's file (sha256 0a445a36d78b6c82...). It then ran 32 harness cases through `tests/golden/harness.py` (`run_case`, cases built with `tests/golden/cases.py`'s helpers and invented names) in three forms: the installed file copied into the case folder (`python repo_traffic.py`), a driver calling the installed module's `cli()` (`repo-traffic`), and a driver using `runpy.run_module` (`python -m repo_traffic`). Seven commands that need no network (`--help`, `--version`, `python -m repo_traffic --version`, four usage errors) ran the real `repo-traffic` executable with no `gh` on PATH and the proxy pointed at a closed port. Outputs: `2026-10-08-wiki-verify.out.txt` (Windows 11, Python 3.14.6) and `2026-10-08-wiki-verify.linux.out.txt` (Ubuntu under WSL 2, Python 3.14.4, installed with uv 0.12.24).

Also on Windows: `pipx install` and `pipx uninstall` (pipx 1.17.12, in scratch `PIPX_HOME`/`PIPX_BIN_DIR`), and both scheduled tasks (`install-task.ps1` and the page's `Register-ScheduledTask` block) registered as `repo-traffic-wiki-verify`, read back and unregistered; neither ever fired. On Linux: `systemd-analyze --user verify` of the two unit files (systemd 259) and `systemd-analyze calendar`. The plist was parsed with `plistlib` only.

Not tested (marked on the pages): macOS, launchd, cron, enabling the systemd timer, `pip install --user`, `pipx ensurepath`, `gh auth login`/`status`, the task commands on the real name, a scheduled task actually firing, a console window from `repo-traffic.exe` under Task Scheduler, a non-writable `site-packages` with `python -m`.

Checks (2026-10-08): `check` 8 pages, 0 errors, 0 warnings; `outputs` 57 checked, 0 missing, 3 skipped (two pytest summaries run by hand, the README's quoted cron line); `snippets` 3 blocks checked, 0 missing, 14 commands; `--check-pages` 51 blocks and commands checked, 0 missing; `tells.py --wiki` 0 strong, 14 weak (long sentences, and two words on its list that are the technical terms here).

The repository's own tests: `python -m pytest` 80 passed, 1 skipped in 36.77 s (Windows, 3.14.6); `REPO_TRAFFIC_SCRIPT=<site-packages of the PyPI install>/repo_traffic.py python -m pytest tests/test_golden.py` 21 passed, 1 skipped. The release run 37878858249 passed every job. `2026-10-08-wiki-verify.py` passes this repository's `ruff check` and `ruff format --check`; pytest does not collect it (`testpaths = ["tests"]`).

## Facts verified while writing (not in the README)

- CSV files end lines with CRLF on every OS; `run.log`, the JSON files, `summary.md` and stdout use CRLF on Windows and LF on Linux. Files are UTF-8 without a BOM.
- `python -m repo_traffic` without `--config` uses the installed module's folder (`site-packages`) as the settings folder: it ignores `repo_traffic.json` in the current folder and writes `data/` into `site-packages` (`if __name__ == "__main__": main(base=HERE)`). With `--config` it works.
- A repository without push access leaves the run `ok`, exit 0; it shows at 0 in the traffic tables and is named under "No traffic access".
- A missing `--config` file logs `FAILED FileNotFoundError(...)` in `data/` beside where the file would be, creating that folder. Invalid JSON logs `FAILED JSONDecodeError(...)`; the message differs between Python versions.
- Unknown settings keys are ignored silently (`"npm-user"` skips npm). `null` counts as unset. `pypi_packages` may be a comma string. `"top": 0` prints headings with no rows.
- `--top` cuts only stdout and `summary.md`; the CSVs keep every row.
- Two runs on one day duplicate the `downloads.csv` and `repos.csv` blocks and overwrite the snapshot folder; `daily.csv` does not grow.
- `daily.csv`: a later run's count replaces the day's earlier one; repositories with no traffic days get no rows; a BOM is read and dropped on rewrite.
- Limits: 1000 repositories (`gh repo list --limit 1000`), the first 100 releases, 250 npm packages (`size=250`), 1000 NuGet results.
- Timings: 1 s after each package; 429 waits `Retry-After` (0 to 120 s) or 10, 20, 30, 40 s; empty bodies the same; dropped connections 5 s; 5 tries; 30 s timeout. Two dead NuGet replicas cost 40 s, a permanently empty npm answer 100 s.
- NuGet: `versions` comes from the replica with the higher total, so it can sum to less than `total`; a stats report 404 leaves `last_6_weeks` empty with no note, other report errors add a note.
- The gap warning counts back to the last `ok` or `partial` line whose failure was not the GitHub repository list.
- pypistats.org names are normalised (`Octo_Helper` -> `octo-helper`); the name as given stays in the files. pypistats.org keeps 180 days and updates daily (its API page).
- pip and pipx install 1.0.0b1 without `--pre` while it is the only version (2026-10-08).
- `install-task.ps1`'s task: `pythonw.exe` beside the first `python` on PATH, interactive logon only, `StartWhenAvailable`, battery allowed, 72-hour limit.
- With `--owner` given and no `gh` on PATH, the repository list's `FileNotFoundError` is an `OSError` in `SOURCE_ERRORS`, so the run would be `partial`, not `FAILED` (read from the code; not run).

## Inaccuracies found in the shipped docs

All wait for the next release (README and CHANGELOG ship in the sdist and reach PyPI only with a release). None fixed here.

1. README, "Schedule it": the cron line `0 9 1,15 * *` leaves 16 or 17 days between the 15th and the 1st in every month but February, so 11 runs a year exceed 14 days, lose one or two days of traffic, and trigger the tool's own gap line (wiki-verify "days between runs" section). The README's own rule is "at least every 13 days". Suggest a weekly line, `0 9 * * 1`, as the wiki does.
2. README, "Schedule it": "The wiki has a launchd agent for macOS and a systemd timer for Linux, both of which catch up after the machine was off." The `launchd.plist` man page promises a missed `StartCalendarInterval` run only after sleep and says nothing about a Mac that was shut down; the systemd claim holds (`Persistent=true`).
3. README, "Use": "When one source fails (npm rate-limits you, a NuGet search server is down), the run ... exits with status 1." One NuGet search replica down is a note on an `ok` line with exit 0 (cases nuget-replica-down, nuget-replica-503); only both down fail NuGet. The CHANGELOG states it correctly.
4. README, "Use": "If the last complete run is more than 14 days old, the run says how many days of GitHub traffic were lost." The line gives the days since the last run that saved GitHub traffic (17 in the gap case), not the days lost (two there), and a `partial` run counts as well as a complete one. The CHANGELOG's wording ("the last run that saved GitHub traffic") is right.
5. README, "Where it looks": lists the command, the file and `--config`, but not `python -m repo_traffic`, which reads and writes inside `site-packages` (a code issue as much as a docs one; plan D2 did not cover the `-m` form).
6. README, "Limits": "The counts come from pypistats.org, without mirrors." The daily figures are filtered to `without_mirrors`; `last_month` comes from `/recent`, which takes no mirrors parameter, and pypistats.org's API page does not say whether it counts mirrors.

## Gotchas

- The golden harness copies a script into a case folder and runs it with `runpy`, so the `repo-traffic` and `-m` forms need a driver file named `repo_traffic.py` that removes its own folder from `sys.path` before importing the installed module.
- The harness's unreachable-host error reads `[Errno 10061] golden harness: host down` on Linux too (the shim makes it); the pages say the text is the stand-in's.
- Never register a test task named `repo-traffic` on the maintainer's PC: a task of that name is the live one. The program uses `repo-traffic-wiki-verify` and skips the task section if a task of that name exists.
- WSL's `/tmp` is cleared when WSL restarts; keep the Linux venv under the scratch folder on C:.
- `ruff check .` in CI covers `ai-docs/notes/*.py`: run ruff on a changed verify program before committing it.

Related: see also [../HANDOFF.md](../HANDOFF.md), [../log.md](../log.md), [../plans/2026-10-08-modernization-and-v1-release.md](../plans/2026-10-08-modernization-and-v1-release.md).
