# repo-traffic

GitHub shows traffic (views, clones, referrers) for the last 14 days and then deletes it. This script saves it before it goes, along with the download counts that GitHub doesn't show on the Traffic tab:

- daily views and clones, with unique counts, for every repo you own
- top referrers and popular pages
- stars, forks and release asset download counts
- npm downloads (daily, last 14 days, and last month) for packages you maintain
- NuGet downloads per version for packages you own

Run it at least every 13 days. Over time you build up a history GitHub doesn't keep.

## Requirements

- Python 3.9 or later (standard library only)
- The [GitHub CLI](https://cli.github.com/), logged in (`gh auth login`) as an account with push access to the repos. GitHub only shows traffic to people who can push.

## Use

```sh
python repo_traffic.py --owner your-login --npm-user your-npm-name --nuget-owner your-nuget-name
```

Every flag is optional. With no `--owner` it uses the logged-in `gh` account, and it skips npm or NuGet when you don't name an account. To avoid typing the flags, copy `repo_traffic.example.json` to `repo_traffic.json` and fill it in. That file is gitignored.

| Flag | Config key | Default |
|---|---|---|
| `--owner` | `owner` | the `gh` login |
| `--npm-user` | `npm_user` | none (npm skipped) |
| `--nuget-owner` | `nuget_owner` | none (NuGet skipped) |
| `--data` | `data` | `data` next to the script |
| `--top` | `top` | 10 |

Each run prints the top-N tables and writes to the data folder:

```
data/
  daily.csv          one row per repo per day: views, unique views, clones, unique clones
  downloads.csv      one row per package per run
  run.log            one line per run, ok or FAILED with the error
  snapshots/2026-10-08/
    github.json      everything the GitHub API returned
    packages.json    everything npm and NuGet returned
    summary.md       the top-N tables as markdown
```

`daily.csv` is merged across runs, so runs that overlap don't create duplicates. The data folder is gitignored because it can include traffic for private repos. Point `--data` at a notes vault or a private repo if you want to keep it somewhere else.

## Schedule it

Windows (registers a Task Scheduler task that runs every 13 days and catches up if the PC was off):

```powershell
pwsh -File install-task.ps1            # -Days 13 -At 09:00 -Name repo-traffic
```

macOS or Linux, with cron (cron can't count 13 days, so run it on the 1st and 15th):

```
0 9 1,15 * * cd /path/to/repo-traffic && python3 repo_traffic.py
```

## Limits

- GitHub doesn't say who viewed or cloned, and it doesn't separate bots from people. Your own CI runs count as clones.
- NuGet publishes all-time totals only. To see recent downloads, compare two runs in `downloads.csv`.
- The npm stats API rate-limits bursts. The script waits a second between packages and backs off on HTTP 429.

## License

MIT
