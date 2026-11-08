---
name: repo-traffic
description: Mark's GitHub repo traffic and package download stats with the local dashboard. Use whenever the user asks how their repos or packages are doing, for stats, traffic, visitors, clones, stars or downloads (npm, NuGet, PyPI, OpenUPM, JSR, GitHub releases), "since last check", "repo traffic update", "most popular repos", "how are my packages doing", or any window (24h, couple of days, week). Always ends with the dashboard rebuilt and opened.
---

# repo-traffic

The clone is `D:/m4bwa/Claude/Projects/Ai/repo-traffic`. The full rules are in its `AGENTS.md`, under "Answering ...".

## Every stats request: capture, build, open

1. `python scripts/dashboard.py capture --window <w>` from the clone. Pick `<w>` from the request: `24h`, `48h` (the default for "since last check", "lately" or "couple of days"), `7d` or `all`. Use `last` only when the previous capture was more than a day ago, because a capture taken earlier the same day leaves it empty.
2. `python scripts/dashboard.py build`
3. Open `data/dashboard.html` in the browser (`start "" "D:/m4bwa/Claude/Projects/Ai/repo-traffic/data/dashboard.html"`).
4. The dashboard and the capture show raw cloners, CI checkouts included. For every repo with a big cloner count, check `data/ci_checkouts.csv` (or report.py's CI column) and say how many are real and how many are CI, so a large raw number never goes unexplained.
5. Paste the capture's two tables with a few lines of commentary. End the reply with `file:///D:/m4bwa/Claude/Projects/Ai/repo-traffic/data/dashboard.html`.

`scripts/report.py` gives only a one-day top-ten. Use it only when the user asks for exactly one day, and still do steps 2 to 5.

Never write ad hoc Python over `data/*.csv`, or query GitHub, npm or NuGet directly, for these answers: numbers fetched that way are not recorded. If capture, build or opening the page fails, say so.

## JSR packages

JSR packages are counted only when named in `jsr_packages` in `repo_traffic.json` (as `@scope/name`; JSR cannot list a publisher's packages). When Mark publishes a new JSR package, add it there. The count sums JSR's two download kinds, `npm_tarball` and `jsr_meta`. A new package with no downloads reads 0, not a failure. To check one package by hand without recording it, use `curl https://api.jsr.io/scopes/<scope>/packages/<name>/downloads`, but stats answers still go through capture.
