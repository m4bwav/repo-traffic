"""Rank repos by unique clones on one UTC day minus their GitHub Actions checkouts.

Usage: python 2026-10-14-ci-clones.py data/daily.csv OWNER YYYY-MM-DD [top]
Prints repo, unique clones, Actions checkouts, Dependabot runs, remaining.
One `Run actions/checkout` step on a hosted runner is about one unique clone;
Dependabot update runs have no checkout step but may clone, so they are shown apart.
"""

import csv
import json
import subprocess
import sys

data, owner, day = sys.argv[1:4]
top = int(sys.argv[4]) if len(sys.argv) > 4 else 10


def gh(path):
    out = subprocess.run(["gh", "api", "--paginate", path], capture_output=True, text=True)
    if out.returncode:
        return []
    # --paginate prints one JSON object per page, back to back
    dec, s, objs, i = json.JSONDecoder(), out.stdout.strip(), [], 0
    while i < len(s):
        o, i = dec.raw_decode(s, i)
        objs.append(o)
        while i < len(s) and s[i].isspace():
            i += 1
    return objs


with open(data, newline="", encoding="utf-8") as f:
    rows = [r for r in csv.DictReader(f) if r["date"] == day and int(r["clones"])]
res = []
for r in rows:
    repo = f"{owner}/{r['repo']}"
    runs = [x for p in gh(f"repos/{repo}/actions/runs?created={day}&per_page=100") for x in p.get("workflow_runs", [])]
    checkouts = dependabot = 0
    for run in runs:
        if " - Update #" in run["name"]:
            dependabot += 1
        for p in gh(f"repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100&filter=all"):
            for j in p.get("jobs", []):
                checkouts += sum(1 for s in j.get("steps") or [] if s["name"].startswith("Run actions/checkout"))
    uniq = int(r["clones_uniques"])
    res.append((max(0, uniq - checkouts), r["repo"], uniq, checkouts, dependabot))
for left, repo, uniq, co, dep in sorted(res, key=lambda x: (-x[0], -x[2]))[:top]:
    print(f"{repo}\t{uniq}\t{co}\t{dep}\t{left}")
