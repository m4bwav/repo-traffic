# Changelog

All notable changes are listed here; the format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [PEP 440](https://peps.python.org/pep-0440/).

Compatibility promise: every file 0.1.0 writes keeps its name, columns and format, so an existing `data/` folder carries on. The golden test in `tests/golden/` replays 18 recorded runs of 0.1.0 on Windows, macOS and Linux and holds this version to them byte for byte, except the changes listed under each version (E1 to E7 in the plan). An existing `downloads.csv` with the six-column header of the first test runs is migrated once to the current header, keeping `downloads.csv.bak`.

## [1.0.0b1]

### Added
- Published on PyPI: `pipx install repo-traffic` gives the `repo-traffic` command. It reads `repo_traffic.json` and writes `data/` in the current folder; `python repo_traffic.py` still uses the script's own folder.
- `--help`, `--version` and `--config PATH`.
- PyPI downloads (pypistats.org) for the projects named in `--pypi-packages` or the `pypi_packages` config key: a `pypi` section in `packages.json`, rows in `downloads.csv` and a summary table.
- `repos.csv`: one row per repo per run with private, fork, stars, forks and release downloads, so stars and forks have a history (E6).
- A gap warning in `run.log`, on stdout and at the top of `summary.md` when the last run that saved GitHub traffic is more than 14 days old (a partial run counts unless the GitHub repo list failed).

### Changed
- One failing source no longer fails the whole run: the rest is saved and merged, `run.log` says `partial` with what failed, the summary lists it, and the exit status is 1 (E2). One NuGet search replica down is a note, not a failure; a replica answering in an unknown shape is a failure. An empty or cut-off answer is retried. HTTP 429 honours `Retry-After` (0 to 120 seconds).
- A repo without push access is named in `run.log`, in the summary ("No traffic access") and as `traffic_error` in `github.json`, instead of showing 0 silently (E3).
- `--help` prints usage instead of taking a snapshot; a flag without its value or an unknown flag is a usage error with exit status 2, and nothing is written (E1).
- A failure before the run starts is logged in the `--data` folder, not in `data/` next to the script (E4).
- `downloads.csv` with an older header is migrated once instead of getting misaligned rows, row by row: the seven-column rows 0.1.0 appended under the six-column header keep their values, six-column rows are mapped by name, and a row of any other width stops the migration with the file untouched. A CSV with an unknown header is left alone and reported (E5). A CSV that starts with a byte order mark (Excel's "CSV UTF-8") is read normally, and an empty `downloads.csv` gets its header before the rows.
- Flags: a repeated flag takes the last value (0.1.0 took the first), and abbreviations such as `--own` are refused.
- With `--config`, the config file's folder is the settings folder: `data/` and relative `--data` paths start there.
- Summary tables break ties by name, so equal counts list the same way every run (E7: a repo without traffic now sorts among the zeros by name).

## [0.1.0] - 2026-10-08

The first version (commit 9b6e754, tag only): GitHub traffic, stars, forks and release downloads; npm and NuGet downloads; `daily.csv`, `downloads.csv`, snapshots, `summary.md` and `run.log`; `install-task.ps1` for Windows.

[1.0.0b1]: https://github.com/m4bwav/repo-traffic/compare/v0.1.0...v1.0.0b1
[0.1.0]: https://github.com/m4bwav/repo-traffic/tree/v0.1.0
