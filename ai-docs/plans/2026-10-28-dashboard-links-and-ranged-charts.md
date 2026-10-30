# Prompt: dashboard links and charts that follow the time range

Paste into a fresh session opened in `D:/m4bwa/Claude/Projects/Ai/repo-traffic`.

---

Read `AGENTS.md`, `ai-docs/INDEX.md` and `scripts/dashboard.py` (the page is built by `render_html` and
`series_payload`; the window selector switches between the precomputed `windows` payloads from `WINDOWS`).
Make two changes to the dashboard page, served by `serve` and written by `build` to `data/dashboard.html`:

1. **Links.** Every repo name in the repo tables links to `https://github.com/<owner>/<repo>`, and every
   package name links to its registry page: npm `https://www.npmjs.com/package/<name>`, NuGet
   `https://www.nuget.org/packages/<id>`, PyPI `https://pypi.org/project/<name>/`, OpenUPM
   `https://openupm.com/packages/<name>/`, and a release asset to its repo's releases page. Take the owner from
   the config or snapshot data, never hardcode `m4bwav`. Open in a new tab (`target="_blank" rel="noopener"`).
   Keep sorting working: sort on the text, not the markup. Escape names in the HTML.

2. **Charts follow the selected window.** Today the charts ignore the time-range selector. When the window
   changes, redraw every chart to show only points from that window's start (`window_bounds`) to now; `all`
   shows everything, `last` shows the span since the previous capture. Daily series (views, clones, npm, PyPI,
   OpenUPM) clip by UTC day; capture-based series (NuGet, stars, forks, releases) clip by capture timestamp and
   keep the newest point at or before the start as the baseline, so a line doesn't start in empty space. If a
   window holds fewer than two points, show a short "not enough data in this window" note instead of an empty
   chart. Send the start bound for each window in the payload so the browser doesn't recompute window rules.

Constraints: no new dependencies or CDN libraries beyond what the page already loads; works offline from the
file; keep the remembered-window behaviour if any. Add or extend tests in `tests/` for the payload (window
start bounds, link URLs per registry, HTML escaping). Run the test suite, then `python scripts/dashboard.py
build`, open `data/dashboard.html`, and check each window in the browser: links resolve and charts change.
Update the README's dashboard paragraph and CHANGELOG, log the work in `ai-docs/log.md`, and open a PR (merge it
yourself once checks pass, per the global rules; this repo publishes to PyPI, so don't cut a release without
asking).
