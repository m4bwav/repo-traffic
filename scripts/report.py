"""Most popular repos on one UTC day: python scripts/report.py [--day YYYY-MM-DD] [--top N] [--no-refresh] [--no-ci]

Answers "what were my most popular repos in the last 24 hours" in one command and a few hundred bytes of output.
- Takes a fresh snapshot first (repo_traffic.py, output hidden) unless today's snapshot folder already exists.
- The day defaults to the latest complete UTC day with traffic (today's UTC row stays empty until well past noon).
- Prints two top-N tables: unique visitors, and unique cloners minus GitHub Actions checkouts (CI clones a repo
  once per `Run actions/checkout` step, so raw clone counts mostly measure how often CI ran).
- Checkout counts are cached per repo and day in data/ci_checkouts.csv (gitignored); finished days never change,
  so asking again costs no API calls. The gh calls run in parallel.
- Records every snapshot folder in data/metrics.csv (scripts/dashboard.py), so each pull is kept for later deltas.
Owner and data folder come from repo_traffic.json, as for repo_traffic.py. Output goes to the console only.
"""

import argparse
import csv
import datetime as dt
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import repo_traffic as rt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dashboard  # noqa: E402

CACHE_HEADER = ["repo", "date", "checkouts", "dependabot"]


def gh_pages(path):
    """Every page of gh api --paginate PATH as a list of objects; [] when gh refuses."""
    out, err = rt.gh_call(["api", "--paginate", path])
    if err:
        return []
    dec, s, objs, i = json.JSONDecoder(), out.strip(), [], 0
    while i < len(s):  # --paginate prints one JSON object per page, back to back
        o, i = dec.raw_decode(s, i)
        objs.append(o)
        while i < len(s) and s[i].isspace():
            i += 1
    return objs


def load_daily(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def busy(r):
    return int(r["views"]) or int(r["clones"])


def pick_day(rows, today):
    """The latest UTC day before today with any traffic, as YYYY-MM-DD, or None."""
    days = [r["date"][:10] for r in rows if r["date"][:10] < today.isoformat() and busy(r)]
    return max(days, default=None)


def load_cache(path):
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {(r["repo"], r["date"]): (int(r["checkouts"]), int(r["dependabot"])) for r in csv.DictReader(f)}


def save_cache(path, cache):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CACHE_HEADER)
        for (repo, day), (co, dep) in sorted(cache.items()):
            w.writerow([repo, day, co, dep])


def checkout_steps(jobs_pages):
    # Only "Run actions/checkout": the "Post Run actions/checkout" cleanup step doubled the count on 2026-10-14.
    return sum(
        1
        for p in jobs_pages
        for j in p.get("jobs", [])
        for s in j.get("steps") or []
        if s["name"].startswith("Run actions/checkout")
    )


def ci_counts(owner, repos, day, pages=gh_pages, workers=8):
    """{repo: (Actions checkouts, Dependabot update runs)} on day, with the gh calls in parallel."""
    with ThreadPoolExecutor(workers) as pool:
        runs = dict(
            zip(
                repos,
                pool.map(lambda r: pages("repos/%s/%s/actions/runs?created=%s&per_page=100" % (owner, r, day)), repos),
            )
        )
        work = [(r, run) for r in repos for p in runs[r] for run in p.get("workflow_runs", [])]
        jobs = pool.map(
            lambda w: pages("repos/%s/%s/actions/runs/%s/jobs?per_page=100&filter=all" % (owner, w[0], w[1]["id"])),
            work,
        )
        out = {r: [0, 0] for r in repos}
        for (r, run), jp in zip(work, jobs):
            out[r][0] += checkout_steps(jp)
            out[r][1] += " - Update #" in run["name"]
    return {r: tuple(v) for r, v in out.items()}


def rank(rows, day, ci):
    table = []
    for r in rows:
        if r["date"][:10] != day or not busy(r):
            continue
        uc = int(r["clones_uniques"])
        co, dep = ci.get(r["repo"], (0, 0))
        table.append(
            dict(repo=r["repo"], visitors=int(r["views_uniques"]), views=int(r["views"]), cloners=uc,
                 ci=co, dependabot=dep, real=max(0, uc - co))
        )  # fmt: skip
    return table


def render(table, day, top, with_ci):
    out = [
        "Repo traffic for %s (UTC)" % day,
        "",
        "Unique visitors:",
        "| # | repo | visitors | views |",
        "|---|---|---|---|",
    ]
    by_v = sorted((t for t in table if t["visitors"]), key=lambda t: (-t["visitors"], -t["views"], t["repo"]))
    out += ["| %d | %s | %d | %d |" % (i, t["repo"], t["visitors"], t["views"]) for i, t in enumerate(by_v[:top], 1)]
    if with_ci:
        out += ["", "Unique cloners minus CI checkouts:", "| # | repo | real | cloners | CI |", "|---|---|---|---|---|"]
        by_c = sorted((t for t in table if t["real"]), key=lambda t: (-t["real"], -t["cloners"], t["repo"]))
        out += [
            "| %d | %s | %d | %d | %d |" % (i, t["repo"], t["real"], t["cloners"], t["ci"])
            for i, t in enumerate(by_c[:top], 1)
        ]
        hidden = sum(t["cloners"] for t in table) - sum(t["real"] for t in table)
        out.append("(%d unique clones were CI checkouts)" % hidden)
    return "\n".join(out)


def refresh(data, today):
    """Run repo_traffic.py once a day, quietly; returns an error line or None."""
    if (data / "snapshots" / today.isoformat()).exists():
        return None
    r = subprocess.run([sys.executable, str(ROOT / "repo_traffic.py")], capture_output=True, text=True, **rt.NO_WINDOW)
    return None if r.returncode == 0 else "snapshot exited %d; using the data already saved" % r.returncode


def main(argv=None, today=None, pages=gh_pages):
    p = argparse.ArgumentParser(description="Most popular repos on one UTC day.")
    p.add_argument("--day", help="UTC day YYYY-MM-DD (default: the latest complete day with traffic)")
    p.add_argument("--top", type=int, default=10, help="rows per table (default: 10)")
    p.add_argument("--no-refresh", action="store_true", help="skip the snapshot, use data/ as it is")
    p.add_argument("--no-ci", action="store_true", help="skip the CI subtraction (no gh calls)")
    args = p.parse_args(argv)
    cfg_path = ROOT / "repo_traffic.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    data = ROOT / cfg.get("data", "data")
    if not args.no_refresh:
        err = refresh(data, dt.date.today() if today is None else today)
        if err:
            print(err)
    dashboard.record(data)
    rows = load_daily(data / "daily.csv")
    utc_today = dt.datetime.now(dt.timezone.utc).date() if today is None else today
    day = args.day or pick_day(rows, utc_today)
    if not day:
        print("no traffic in %s" % (data / "daily.csv"))
        return 1
    ci = {}
    if not args.no_ci:
        cache_path = data / "ci_checkouts.csv"
        cache = load_cache(cache_path)
        cloned = sorted({r["repo"] for r in rows if r["date"][:10] == day and int(r["clones"])})
        missing = [r for r in cloned if (r, day) not in cache]
        if missing:
            owner = cfg.get("owner") or rt.gh_login()
            fresh = ci_counts(owner, missing, day, pages)
            if day < utc_today.isoformat():  # a finished day never changes; today's would
                cache.update({(r, day): v for r, v in fresh.items()})
                save_cache(cache_path, cache)
            ci = {**{r: cache[(r, day)] for r in cloned if (r, day) in cache}, **fresh}
        else:
            ci = {r: cache[(r, day)] for r in cloned}
    print(render(rank(rows, day, ci), day, args.top, not args.no_ci))
    return 0


if __name__ == "__main__":
    sys.exit(main())
