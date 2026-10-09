# Handoff

State (2026-10-08, end of the first session): the package-modernize run toward 1.0.0 has finished Phases 0 to 4 on branch `v1`; pull request #1 (https://github.com/m4bwav/repo-traffic/pull/1) is green on every CI row and waits for the maintainer's merge (the agent's merge was refused by the auto-mode classifier). Plan: [plans/2026-10-08-modernization-and-v1-release.md](plans/2026-10-08-modernization-and-v1-release.md); evidence: [log.md](log.md).

Done: survey, golden recording of 0.1.0 (`tests/golden/`, commit 896876d), the plan (ruled 2026-10-08: PyPI yes, all else as recommended, plus E7 found later), the rewrite (543 lines, 59 unit tests at 99 percent branch coverage, golden test with per-OS exceptions files, canary seen red), CI (ci.yml, 15 jobs), release.yml (gated by the `pypi` environment), the independent review (12 findings fixed), settings and rulesets, tag v0.1.0 (tag only), README images (banner and chart), SECURITY.md, CHANGELOG, AGENTS.md. PyPI: the maintainer turned on 2FA and the pending publisher is registered (repo-traffic, m4bwav/repo-traffic, release.yml, environment pypi).

Next, in order:
1. After the merge: `git -C <clone> switch master && git -C <clone> pull --ff-only`, wait for ci on master, then tag `v1.0.0b1` on the merge commit and push the tag. The release run stops at the `pypi` environment for the maintainer's approval (Review deployments). After approval: check the verify job (three OSes), `pip index versions repo-traffic --pre`, the Release assets and attestations, and that the README images load from the tag on GitHub and on pypi.org.
2. 1.0.0: a pull request that sets `__version__ = "1.0.0"`, the classifier back to "5 - Production/Stable", the CHANGELOG heading `## [1.0.0] - <date>` with the 1.0.0b1 notes moved under it, and the README image URLs pinned to `v1.0.0`; merge after ci, tag `v1.0.0`, approval, verify.
3. Wiki through wikiwright, headless (`claude -p`), working copy `D:\m4bwa\Claude\Projects\Ai\repo-traffic.wiki`, scratch under `%TEMP%\rt\run`. wikiwright has no PyPI scaffold: write the verification program in Python (install `repo-traffic==1.0.0` from PyPI into a scratch venv, run every page example through `tests/golden/harness.py` with invented fixtures, save the output), then file that gap in wikiwright.
4. On the maintainer's PC: pull the clone to the tag (the task's path, `repo_traffic.py` in the clone, is unchanged), run the `repo-traffic` task once from Task Scheduler, check that run.log's last line is `ok` (or a `partial` that names only a known source) and that `data/daily.csv` gained rows.
5. Wrap-up: this file, the log, the decision record, the inventory row and the kickoff prompt's corrections in the private package-modernization repository.

Gotchas:
- Never edit `tests/golden/` except the two exceptions files, and only for a ruled change; when a golden case fails, fix `repo_traffic.py`.
- `data/` and `repo_traffic.json` hold private names: never open them beyond a CSV header, never commit them.
- The auto-mode classifier refuses `gh pr merge` and even `gh pr edit --add-assignee` after a refused merge in the same session: ask the maintainer to merge.
- Python edits on Windows: text mode writes CRLF (`write_bytes` for repository files); heredocs turn `\\n` into a newline, so edit code with the Edit tool.
