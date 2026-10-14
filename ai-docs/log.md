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

## [2026-10-08] update | Phases 3 and 4: review, settings, images

- Pull request m4bwav/repo-traffic#1. CI run 37876544059 on 99a1d3c: all 15 jobs green (10 test rows, lint, 3 installed-wheel rows, ci).
- Independent review (package-modernize prompts/review-subagent.md, read only, about 7 minutes): 12 findings, two bugs (the E5 migration lost the values of 0.1.0's seven-column rows; the gap warning ignored partial runs that saved GitHub). All fixed with tests in 2368555 (59 unit tests); summary posted on the pull request.
- Settings: topics, homepage (PyPI page), delete branch on merge, Dependabot alerts and security updates on; environment `pypi` with m4bwav as required reviewer and a `v*` tag rule; rulesets 24764956 (master: no deletion, no force push, required check ci, admin bypass) and 24764961 (tags only by admins). Tag v0.1.0 on 9b6e754 (tag only).
- Images: docs/images/banner.jpg (ComfyUI 0.38.2 on the Mac, Z-Image Turbo, 1536x512, seed 33 of 11/22/33/44, 38 KB) and daily-views.png (chartwright, Vega-Lite line chart of sample-daily.csv, which make_sample_data.py builds by running repo-traffic through the golden harness on invented data; quantized to 44.5 KB). check-readme-images.mjs: every image works (raw URLs pinned to v1.0.0b1, live once the tag exists).
- PyPI: the maintainer's account has no 2FA yet, so the Publishing page redirects to the two-factor setup; the pending publisher waits for it. The release (Phases 5 and 6) waits for both.
- Skill lessons: m4bwav/package-modernize#39 (templates/pypi, references/pypi.md "First run", L-160 to L-166), assigned for review.

## [2026-10-08] update | Wiki for 1.0.0b1 (wikiwright Steps 1 to 6 and 8)

- Preflight: placeholder (d6a39f0). Eight pages, sidebar and footer written in the wiki working copy; not committed, not pushed (the maintainer's session publishes and runs `live`).
- Verified against repo-traffic 1.0.0b1 from PyPI with notes/2026-10-08-wiki-verify.py: 32 golden-harness cases in three forms (file, `cli()`, `runpy` for `-m`) plus 7 real-command cases, on Windows 3.14.6 and WSL Ubuntu 3.14.4; pipx install and uninstall; both Windows tasks registered under a test name, read back, removed; systemd units checked with systemd-analyze. Outputs saved beside it.
- Checks: wikiwright check 0 errors, outputs 57 checked 0 missing, snippets 0 missing, the program's --check-pages 51 checked 0 missing, tells 0 strong. Repository tests 80 passed 1 skipped; golden test against the PyPI install 21 passed 1 skipped.
- Found: `python -m repo_traffic` without `--config` writes `data/` into site-packages; the README's 1st-and-15th cron line exceeds 14 days 11 times a year; five more README/CHANGELOG points. Details: notes/2026-10-08-github-wiki.md.
## [2026-10-08] index | rebuilt (3 entries)

## [2026-10-11] run | traffic snapshot

Ran `python repo_traffic.py` (ok, 65 repos, 7 npm, 7 NuGet). Full table of every repo with traffic written to data/reports/2026-10-11-traffic.md (gitignored). Note: the console summary stops at the top 10, so a full list needs github.json from the snapshot; summing daily uniques from daily.csv overcounts against GitHub's 14-day uniques. PyPI is not set in repo_traffic.json, so repo-traffic's own PyPI downloads are not collected.

## [2026-10-11] add | OpenUPM downloads (PR #3)

Branch openupm-downloads (worktree ../repo-traffic-openupm), https://github.com/m4bwav/repo-traffic/pull/3, merged 2026-10-11: `--openupm-packages` / `openupm_packages`, counts from package.openupm.com npm-style routes, shared `npm_style_downloads`, golden E1 help text updated in both exceptions files. 82 tests pass, coverage 99%. repo_traffic.py 642 lines = yellow size band (was 594). Local repo_traffic.json now names com.m4bwav.universe-generator (ignored by master code until the merge). Wiki needs an OpenUPM line at its next update. Open Dependabot alert #1 (pytest tmpdir) predates this.

## [2026-10-11] update | codex_plugins: OpenAI plugin directory listings

- Research ([notes/2026-10-11-codex-plugin-directory.md](notes/2026-10-11-codex-plugin-directory.md)): the directory ChatGPT and Codex share has public listing pages (`chatgpt.com/plugins/<id>`) but no API, install counts or ratings. Built `codex_plugins` (config only, so the golden `--help` text is unchanged): listed yes/no, name and version per run in `codex.csv` and `packages.json`. chatgpt.com's Cloudflare check refuses urllib's default TLS context (post-handshake auth), so those requests use their own context, and a `cf-mitigated` 403 is retried. The script is exactly at the 600-line green limit (module docstring shortened to make room). 86 tests pass, coverage 99 percent, size green, on branch codex-directory.
## [2026-10-11] index | rebuilt (3 entries)
## [2026-10-11] index | rebuilt (4 entries)
## [2026-10-13] note | three-day popularity check

- Ran a manual snapshot (ok, 67 repos) and summed `daily.csv` rows dated 2026-10-11 to 10-13 for views and clones. For NuGet, the `total` column did not change between the 10-11 and 10-13 snapshots while `last_6_weeks` rose (RandomNameGeneratorLibrary +2,728), so a short-window NuGet count comes from the `last_6_weeks` delta, not `total`. The npm range API had not yet published 10-12 (all zeros) on 10-13; npm lags about a day.
## [2026-10-14] note | last-24-hours popularity check

- Ran a manual snapshot at 12:40 UTC (ok, 69 repos). `daily.csv` had no rows for 2026-10-14 yet: GitHub's traffic API leaves the current UTC day empty well into the day, so "the last 24 hours" means the latest complete UTC day (2026-10-13 here). Ranked by `views_uniques`, then `views`. Clone counts are mostly CI runners, bots and agent sessions (one repo had 72 clones and 1 view), so don't rank by them. The columns are `views_uniques` and `clones_uniques` (plural), not `views_unique`.

## [2026-10-14] note | unique clones minus CI checkouts

- Mark asked for repos ranked by unique clones minus their pipelines' clones on 2026-10-13. Method ([notes/2026-10-14-ci-clones.py](notes/2026-10-14-ci-clones.py)): for each repo with clones that day, `gh api repos/OWNER/REPO/actions/runs?created=DAY`, then the jobs of each run; count the `Run actions/checkout` steps (the `Post Run actions/checkout` step must not be counted again). Each hosted-runner job clones from its own IP, so one checkout is about one unique clone. Dependabot update runs have no checkout step but may clone; they are reported separately. Result: in five repos, CI checkouts equalled or exceeded the day's unique clones. The repos left at the top had no CI runs that day, so their clones are probably plugin installs and updates (Claude Code clones a plugin's repo) plus Mark's own machines and agent sessions. Plan: [plans/2026-10-14-ci-clone-subtraction.md](plans/2026-10-14-ci-clone-subtraction.md).
## [2026-10-14] index | rebuilt (5 entries)
## [2026-10-14] index | rebuilt (5 entries)
