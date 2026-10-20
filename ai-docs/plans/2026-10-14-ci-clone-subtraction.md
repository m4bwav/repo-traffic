---
title: CI clone subtraction and a popularity report
kind: plan
status: done
date: 2026-10-14
verified: 2026-10-14
stale_after: 2027-01-14
tags: [plan, clones, github-actions, report, feature]
summary: "built 2026-10-20 as scripts/report.py: rank repos on one complete UTC day by unique views and by unique clones minus GitHub Actions checkouts, so popularity questions stop needing ad-hoc scripts"
---

# CI clone subtraction and a popularity report

Related: builds on [notes/2026-10-14-ci-clones.py](../notes/2026-10-14-ci-clones.py); see also [log.md](../log.md) (entries of 2026-10-11, 10-13 and 10-14).

## Goal

Answer "what are my most popular repos lately" with one command, with CI clones taken out.

## Status

Done 2026-10-20 as a separate `scripts/report.py` (one UTC day, `--day` to pick another), so `repo_traffic.py` stays at 647 lines. Mark asked on 2026-10-20 to add whatever cuts the token cost of the question; that settled the open question below. The note script stays as the record of the method. Not built: a `ci_checkouts` column in `daily.csv` during scheduled runs, and multi-day reports (summing daily uniques double-counts people).

## Why

The maintainer asked "which repos are most popular" on three dates (2026-10-11, 10-13, 10-14). Each time the agent wrote throwaway Python over `daily.csv`. Clone counts are dominated by CI: on 2026-10-13, Actions checkouts equalled or exceeded the unique clones in five repos, so ranking by raw clones mostly measures how often the CI ran. The 10-14 answer took two ad-hoc scripts (about 60 s of `gh api` calls for 33 repos) plus a correction, because a "checkout" substring match also counted the `Post Run actions/checkout` step and doubled the result.

## What

A `--report DAYS` mode (or a `report` subcommand) that reads `data/daily.csv`, uses the last DAYS complete UTC days (the current UTC day is often still empty at midday), and prints two top-N tables: unique views, and unique clones minus Actions checkouts. Checkouts are counted from `actions/runs?created=<day>` and each run's jobs, as the note script does: only steps whose name starts with `Run actions/checkout`. Dependabot update runs are shown in their own column, not subtracted. Optionally save the per-day checkout count in a new `ci_checkouts` column at the end of `daily.csv` during normal runs, since Actions run history is kept longer than traffic but not for ever.

## Constraints

- `repo_traffic.py` is 647 lines, already in the yellow size band (green up to 600, red over 800). This feature probably adds 40 to 60 lines; the maintainer should rule on the size, or the report could live in a separate optional script.
- Unit tests fake `gh`; the golden `--help` text changes if a flag is added (a ruled exception E-n).
- Public repo: the report must print to the console or the gitignored data folder only.

## Next single action

None. Reopen if Actions run history turns out too short to cover days asked about later (then record checkouts during the scheduled run).
