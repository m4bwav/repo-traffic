"""Builds docs/images/sample-daily.csv: the daily.csv repo-traffic writes after
three runs 13 days apart, on invented traffic for invented repos, through the
golden harness (fake gh, no network). The README's chart is drawn from it.

Usage: python docs/images/make_sample_data.py
"""

import datetime
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "golden"))
import harness  # noqa: E402
from cases import OWNER, github  # noqa: E402

REPOS = [
    {"name": n, "isPrivate": False, "isFork": False, "stargazerCount": 0, "forkCount": 0}
    for n in ("alpha-lib", "beta-tool", "gamma-cli")
]
LEVEL = {"alpha-lib": 40, "beta-tool": 18, "gamma-cli": 8}


def window(end, rng, repo):
    """GitHub's 14 daily rows ending the day before end."""
    rows = {"views": [], "clones": []}
    for i in range(14, 0, -1):
        day = end - datetime.timedelta(days=i)
        weekend = day.weekday() >= 5
        base = LEVEL[repo] * (0.5 if weekend else 1.0) * (1 + 0.02 * (day - datetime.date(2026, 8, 1)).days)
        views = max(0, int(rng.gauss(base, base / 4)))
        clones = max(0, int(rng.gauss(base / 5, base / 12)))
        for kind, n in (("views", views), ("clones", clones)):
            rows[kind].append({"timestamp": day.isoformat() + "T00:00:00Z", "count": n, "uniques": max(0, n * 2 // 5)})
    return {
        k: {"count": sum(r["count"] for r in v), "uniques": max(r["uniques"] for r in v), k: v} for k, v in rows.items()
    }


def main():
    rng = random.Random(20261008)
    runs = []
    for end in (datetime.date(2026, 9, 12), datetime.date(2026, 9, 25), datetime.date(2026, 10, 8)):
        traffic = {r["name"]: window(end, rng, r["name"]) for r in REPOS}
        runs.append(
            {
                "now": end.isoformat() + "T09:00:00",
                "args": ["--owner", OWNER],
                "gh": github(repos=REPOS, traffic=traffic),
                "http": {},
                "down": [],
            }
        )
    record = harness.run_case(ROOT / "repo_traffic.py", {"config": None, "files": {}, "runs": runs})
    csv_text = record[-1]["files"]["data/daily.csv"].replace("\r\n", "\n")
    (Path(__file__).parent / "sample-daily.csv").write_bytes(csv_text.encode("utf-8"))
    print("wrote sample-daily.csv: %d rows" % (csv_text.count("\n") - 1))


if __name__ == "__main__":
    main()
