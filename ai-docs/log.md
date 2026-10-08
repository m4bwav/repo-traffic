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
