# Log

## 2026-10-08 - first version

- Built repo_traffic.py: GitHub traffic (views, clones, referrers, paths), stars, forks, release asset downloads, npm downloads, NuGet downloads per version. Writes JSON snapshots, a merged daily.csv, downloads.csv, a markdown summary and run.log.
- Account names live in the gitignored repo_traffic.json, so the script itself has nothing personal in it.
- Findings: the npm search API finds packages by npm username (`maintainer:`), not GitHub login. The npm stats API returns empty bodies when hit in a fast loop, so the script sleeps 1 s per package and retries 429. NuGet search (`q=owner:NAME`) gives all-time totals only.
- install-task.ps1 registers a Windows task every 13 days with StartWhenAvailable, running pythonw. gh calls use CREATE_NO_WINDOW so no console flashes.

## 2026-10-08 - NuGet counts were wrong

- The first version read NuGet totals from one search replica (azuresearch-usnc), which said 0 for UniverseGenerator while nuget.org showed 251. The other replica (ussc) said 183, and usnc trailed on every package (3,894,453 vs 3,923,964 for the biggest).
- Fix: query both replicas and keep the higher total, add `www.nuget.org/stats/reports/packages/ID?groupby=Version` (the JSON behind "Full stats": last 6 weeks, facts by version and client), and take the max of all three for the all-time figure, since search can trail even the 6-week number for a new package.
- downloads.csv gained a last_6_weeks column; the first test rows were deleted and rewritten.

## 2026-10-08 - first report

- A hand-written report of the first snapshot went to `data/reports/` (gitignored, like the rest of `data/`). A report generator is a candidate for the modernization run (kickoff in the private package-modernization repo, `prompts/2026-10-08-repo-traffic-kickoff.md`).
## [2026-10-08] create | Phase 0: survey and golden recording of 9b6e754

- Branch `v1` off master 9b6e754. Survey: `survey-github.sh m4bwav/repo-traffic` saved as ai-docs/notes/2026-10-08-survey-github.txt; findings in ai-docs/notes/2026-10-08-survey.md. PyPI name `repo-traffic` free (pypi.org JSON 404).
- Golden recording: tests/golden/ (frozen original, blob ddb17b44 checked by capture.py; 18 cases with a fake gh, a local HTTP server, a fixed clock, recorded sleeps and a 127.0.0.1-only socket guard). `python tests/golden/capture.py` on Windows (3.14.6) and in WSL (3.14.4): "18 cases, recorded twice, identical". `capture.py --check` passes on 3.9.25 and 3.12.14. Windows and Linux differ only in line endings.
- everlast registered (mode repo, sync push); AGENTS.md got the everlast block; .github/copilot-instructions.md added.
## [2026-10-08] index | rebuilt (1 entries)
## [2026-10-08] index | rebuilt (2 entries)

## [2026-10-08] update | Phase 1: plan with decisions D1-D18, exceptions E1-E5; stopped for the ruling

## [2026-10-08] update | Ruling: D3 yes, the rest as recommended

- Quote: "I'll try to setup pypi account, do everything else that you can". PyPI account and pending publisher are the maintainer's (unconfirmed until the 1.0.0b1 publish job runs).

## [2026-10-08] update | Phase 2: rewrite on v1

- Rewrite in repo_traffic.py (543 lines, stdlib only): argparse, isolated source failures, repos.csv, PyPI via pypistats.org, gap warning, CSV header migration, name tie-break. 283d465, 663af0b, 7d3b176.
- Golden exceptions: Windows file written by the test and reviewed field by field; posix file written on ubuntu-24.04 and macos-latest by a throwaway workflow on branch golden-posix-scratch (run 37875372415; both artifacts sha256 fe5c0d2c..., matching the logged hashes; capture.py --check passed on macOS too). posix and Windows differ only in line endings (scratch compare script). Branch deleted after.
- New exception E7 found while writing them: the name tie-break reorders gamma-private (no access, 0/0) after delta-empty in no-push-access; the plan said no recorded tie would change. Added to the plan and the pull request's For review list.
- Canary: `+ 1` planted in release_total, golden test 14 failed / 7 passed; `git checkout -- repo_traffic.py`, 21 passed. `git diff --exit-code 896876d` on the recording files: empty.
- Unit tests: 47, branch coverage 99 percent. Size: 543 lines, wheel 11.7 KB, 0 dependencies (green). lint-workflows.sh: WORKFLOWS CLEAN.
- Fresh clone of v1: CI commands on Python 3.9.25 (failed once: argparse on 3.9 titles help "optional arguments:"; fixed with a named "options" group) and 3.14.6: 68 passed, ruff clean, build and twine PASSED.
