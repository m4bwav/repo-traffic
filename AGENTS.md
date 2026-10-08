# repo-traffic

One script, `repo_traffic.py` (Python standard library plus the `gh` CLI), that saves GitHub traffic and npm/NuGet download counts before GitHub's 14-day window drops them. `install-task.ps1` schedules it on Windows. The README covers usage.

Rules:
- `data/` and `repo_traffic.json` are gitignored and must stay that way. They hold private repo traffic and account names. Never commit them or paste their contents into issues or PRs.
- Keep the script stdlib-only and a single file.
- Record what changed and why in `ai-docs/log.md`; `ai-docs/HANDOFF.md` is the starting point for the next session.
