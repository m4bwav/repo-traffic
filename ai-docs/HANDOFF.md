# Handoff

State (2026-10-08): the package-modernize run toward 1.0.0 is on branch `v1`, stopped at the Phase 1 plan review. Phase 0 is done: survey in [notes/2026-10-08-survey.md](notes/2026-10-08-survey.md), golden recording of 9b6e754 in `tests/golden/` (commit 896876d). The plan with decisions D1-D18 and exceptions E1-E5 is [plans/2026-10-08-modernization-and-v1-release.md](plans/2026-10-08-modernization-and-v1-release.md).

Next: take the maintainer's ruling (silence means the recommendations stand), write it into the plan's decisions table, then Phase 2 (rewrite with the golden test first).

The scheduled task `repo-traffic` on the author's PC still runs master's `repo_traffic.py` every 13 days (next 2026-10-21); keep that path working.

Gotchas:
- The recordings and everything else in `tests/golden/` except the future `exceptions.json` never change after 896876d.
- `data/` and `repo_traffic.json` hold private names: never open them beyond a CSV header, never commit them.
