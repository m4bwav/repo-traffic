# repo-traffic

One script, `repo_traffic.py` (Python 3.9+, standard library plus the `gh` CLI), that saves GitHub traffic and npm, NuGet and PyPI download counts before GitHub's 14-day window drops them. It is published on PyPI as `repo-traffic` (a single module with a `repo-traffic` console command). `install-task.ps1` schedules it on Windows. The README covers usage; the wiki covers every file and column.

Layout:
- `repo_traffic.py`: the whole tool. `pyproject.toml`: packaging (hatchling, version read from `__version__`), ruff, pytest and coverage settings.
- `tests/test_unit.py`: every function, with gh, HTTP and sleep faked in process. `tests/test_golden.py`: the golden test.
- `tests/golden/`: the recording of 0.1.0 (commit 9b6e754) and the harness that made it (a fake gh, a local HTTP server, a fixed clock, a 127.0.0.1-only socket guard). `exceptions-windows.json` and `exceptions-posix.json` list the ruled differences (E1 to E7, see the plan in `ai-docs/plans/`).
- `scripts/check_size.py`: the size budget. `.github/workflows/`: `ci.yml` (the required check `ci`) and `release.yml` (tag, attest, approval at the `pypi` environment, PyPI, GitHub Release, verify).

Commands (from the repository root):
- `python -m pip install -r requirements-dev.txt`
- `python -m pytest` (all tests; about 30 s, the golden cases run the script as a process)
- `python -m coverage run -m pytest && python -m coverage report` (90 percent floor)
- `python -m ruff check . && python -m ruff format --check .`
- `python -m build && python -m twine check --strict dist/* && python scripts/check_size.py`
- `python tests/golden/capture.py --check` (the recording still describes the original on this OS)

Rules:
- `data/` and `repo_traffic.json` are gitignored and must stay that way. They hold private repo traffic and account names. Never commit them or paste their contents into issues, pull requests, CI logs, the wiki or images; fixtures use invented names only.
- Keep the script stdlib-only and a single file, inside the size budget (green up to 600 lines, red over 800; wheel green up to 25 KB).
- Never edit `tests/golden/` except the two exceptions files, and those only for a change the maintainer ruled on (write them with `REPO_TRAFFIC_WRITE_EXCEPTIONS=1 python -m pytest tests/test_golden.py`, review, and keep Windows and posix in step). When the golden test fails, fix `repo_traffic.py`.
- No test reaches the real GitHub, npm, NuGet or pypistats APIs.
- File formats only grow: new CSV columns go at the end, with the old header added to the migration list.
- Releases: bump `__version__` and the CHANGELOG in a pull request, wait for `ci` on master, tag `v<version>`; the maintainer approves the `pypi` environment. Nothing is published from a developer machine.
- Record what changed and why in `ai-docs/log.md`; `ai-docs/HANDOFF.md` is the starting point for the next session.

## everlast (session knowledge, load on demand)

- `ai-docs/INDEX.md` lists what past sessions learned here (solutions with verified commands, decisions with reasons, plans). At the start of a task, scan it and open only the entries whose title or tags match; no line matches: `everlast.py search "<key terms>"` before concluding nothing was recorded. Read `ai-docs/HANDOFF.md` when continuing unfinished work (everlast-resume skill).
- Before acting on an entry marked `(recheck due)`, run `everlast.py recheck <entry>`, re-run its Verified-by command only when that is read-only or safe (a build, a test, a version query), then record `everlast.py verify <entry>` or `verify <entry> --failed "what broke"`; a fix that changed is superseded, never reused blindly.
- Before finishing a task that hit a dead end, verified a non-obvious command, made a design choice, or taught you something about the user, record it (everlast-capture skill, or `everlast.py note` / `handoff`); rewrite `HANDOFF.md` when work is left unfinished. Say "nothing to record" when that is true.
- Anything naming a person, an internal host or name, a credential, or an opinion about people goes to the private sidecar (`--private`), never here. Lessons about the user or this machine go to the user tier (`--user`).
- Rules go in this file, system layout in CODEMAP.md; the doc set holds only what could not be re-derived from the code in a minute.
- Link documents together with relative markdown links: every markdown folder is reachable from an index whose lines say when to read each file (`ai-docs/INDEX.md` is generated from frontmatter; give entries a one-line `summary`), and an entry links the entries it relates to on a typed `Related:` line (`supersedes`, `contradicts`, `builds on`, `see also`). The set then reads as a graph for people in Obsidian and for agents alike. No wikilinks in the repo.
