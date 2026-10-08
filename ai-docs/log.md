# Log

## 2026-10-08 - first version

- Built repo_traffic.py: GitHub traffic (views, clones, referrers, paths), stars, forks, release asset downloads, npm downloads, NuGet downloads per version. Writes JSON snapshots, a merged daily.csv, downloads.csv, a markdown summary and run.log.
- Account names live in the gitignored repo_traffic.json, so the script itself has nothing personal in it.
- Findings: the npm search API finds packages by npm username (`maintainer:`), not GitHub login. The npm stats API returns empty bodies when hit in a fast loop, so the script sleeps 1 s per package and retries 429. NuGet search (`q=owner:NAME`) gives all-time totals only.
- install-task.ps1 registers a Windows task every 13 days with StartWhenAvailable, running pythonw. gh calls use CREATE_NO_WINDOW so no console flashes.
