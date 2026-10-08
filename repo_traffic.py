"""Snapshot GitHub traffic and package downloads for every repo you own.

GitHub keeps traffic for 14 days only, so run this at least every 13 days.
Each run writes, under the data directory:

  snapshots/YYYY-MM-DD/github.json   per repo: daily views and clones,
                                     referrers, popular paths, stars, forks,
                                     release asset downloads
  snapshots/YYYY-MM-DD/packages.json npm daily downloads, NuGet downloads
                                     per version
  snapshots/YYYY-MM-DD/summary.md    top-N tables for that run
  daily.csv      one row per repo per day, merged across runs
  downloads.csv  one row per package per run
  run.log        one line per run

Needs Python 3.9+ and the gh CLI, logged in as an account with push access
to the repos (GitHub only shows traffic to those). Standard library only.
Settings come from repo_traffic.json next to this script (see
repo_traffic.example.json) and the flags below, flags winning.

Usage: python repo_traffic.py [--owner NAME] [--npm-user NAME]
           [--nuget-owner NAME] [--data DIR] [--top N]
"""
import csv
import datetime as dt
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = {"owner": None, "npm_user": None, "nuget_owner": None, "data": "data", "top": 10}
DATA = HERE / "data"
# Keeps gh from flashing a console window when the scheduler runs pythonw.
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def gh(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8", **NO_WINDOW)
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)


def http_json(url, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "repo-traffic"})
            with urllib.request.urlopen(req, timeout=30) as f:
                return json.load(f)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429 and i < tries - 1:
                time.sleep(10 * (i + 1))
                continue
            raise
        except urllib.error.URLError:
            if i < tries - 1:
                time.sleep(5)
                continue
            raise


def repos():
    r = subprocess.run(["gh", "repo", "list", CFG["owner"], "--limit", "1000", "--json",
                        "name,isPrivate,isFork,stargazerCount,forkCount"],
                       capture_output=True, text=True, encoding="utf-8", check=True, **NO_WINDOW)
    return json.loads(r.stdout)


def github_snapshot():
    out = {}
    for repo in repos():
        full = f"{CFG['owner']}/{repo['name']}"
        releases = gh(f"repos/{full}/releases?per_page=100") or []
        out[repo["name"]] = {
            "private": repo["isPrivate"],
            "fork": repo["isFork"],
            "stars": repo["stargazerCount"],
            "forks": repo["forkCount"],
            "views": gh(f"repos/{full}/traffic/views?per=day"),
            "clones": gh(f"repos/{full}/traffic/clones?per=day"),
            "referrers": gh(f"repos/{full}/traffic/popular/referrers"),
            "paths": gh(f"repos/{full}/traffic/popular/paths"),
            "release_downloads": {
                rel["tag_name"]: {a["name"]: a["download_count"] for a in rel.get("assets", [])}
                for rel in releases
            },
        }
    return out


def packages_snapshot(today):
    npm, nuget = {}, {}
    if CFG["npm_user"]:
        search = http_json("https://registry.npmjs.org/-/v1/search?size=250&text=maintainer:" + CFG["npm_user"])
        start = (today - dt.timedelta(days=14)).isoformat()
        end = (today - dt.timedelta(days=1)).isoformat()
        for obj in search["objects"]:
            name = obj["package"]["name"]
            rng = http_json(f"https://api.npmjs.org/downloads/range/{start}:{end}/{name}") or {}
            month = http_json(f"https://api.npmjs.org/downloads/point/last-month/{name}") or {}
            npm[name] = {"daily": rng.get("downloads", []), "last_month": month.get("downloads", 0)}
            time.sleep(1)
    if CFG["nuget_owner"]:
        data = http_json("https://azuresearch-usnc.nuget.org/query?take=1000&prerelease=true&q=owner:"
                         + CFG["nuget_owner"])
        for d in data["data"]:
            nuget[d["id"]] = {"total": d["totalDownloads"],
                              "versions": {v["version"]: v["downloads"] for v in d["versions"]}}
    return {"npm": npm, "nuget": nuget}


def merge_daily_csv(gsnap):
    path = DATA / "daily.csv"
    rows = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows[(r["repo"], r["date"])] = r
    for name, d in gsnap.items():
        for kind in ("views", "clones"):
            for day in (d[kind] or {}).get(kind, []):
                key = (name, day["timestamp"][:10])
                r = rows.setdefault(key, {"repo": name, "date": key[1]})
                r[kind] = day["count"]
                r[kind + "_uniques"] = day["uniques"]
    fields = ["repo", "date", "views", "views_uniques", "clones", "clones_uniques"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for key in sorted(rows):
            w.writerow({k: rows[key].get(k, 0) for k in fields})


def release_total(d):
    return sum(sum(a.values()) for a in d["release_downloads"].values())


def append_downloads_csv(psnap, gsnap, today):
    path = DATA / "downloads.csv"
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["snapshot", "registry", "package", "last_14_days", "last_month", "total"])
        for name, d in psnap["npm"].items():
            w.writerow([today, "npm", name, sum(x["downloads"] for x in d["daily"]), d["last_month"], ""])
        for name, d in psnap["nuget"].items():
            w.writerow([today, "nuget", name, "", "", d["total"]])
        for name, d in gsnap.items():
            if release_total(d):
                w.writerow([today, "github-release", name, "", "", release_total(d)])


def top_tables(gsnap, psnap, n):
    def u(d, k):
        return (d[k] or {}).get("uniques", 0), (d[k] or {}).get("count", 0)

    tables = [
        ("Unique cloners, last 14 days", ["Repo", "Unique cloners", "Clones"],
         sorted(((k, *u(d, "clones")) for k, d in gsnap.items()), key=lambda r: (-r[1], -r[2]))),
        ("Unique visitors, last 14 days", ["Repo", "Unique visitors", "Views"],
         sorted(((k, *u(d, "views")) for k, d in gsnap.items()), key=lambda r: (-r[1], -r[2]))),
        ("npm downloads", ["Package", "Last 14 days", "Last month"],
         sorted(((k, sum(x["downloads"] for x in d["daily"]), d["last_month"])
                 for k, d in psnap["npm"].items()), key=lambda r: -r[1])),
        ("NuGet downloads, all time", ["Package", "Total"],
         sorted(((k, d["total"]) for k, d in psnap["nuget"].items()), key=lambda r: -r[1])),
        ("GitHub release asset downloads, all time", ["Repo", "Downloads"],
         sorted(((k, release_total(d)) for k, d in gsnap.items() if release_total(d)), key=lambda r: -r[1])),
    ]
    out = []
    for title, head, rows in tables:
        if not rows:
            continue
        out += [f"## {title}", "", "| # | " + " | ".join(head) + " |", "|---|" + "---|" * len(head)]
        out += ["| %d | " % i + " | ".join(f"{x:,}" if isinstance(x, int) else str(x) for x in r) + " |"
                for i, r in enumerate(rows[:n], 1)]
        out.append("")
    return "\n".join(out)


def configure(argv):
    path = HERE / "repo_traffic.json"
    if path.exists():
        CFG.update(json.loads(path.read_text(encoding="utf-8")))
    flags = {"--owner": "owner", "--npm-user": "npm_user", "--nuget-owner": "nuget_owner",
             "--data": "data", "--top": "top"}
    for flag, key in flags.items():
        if flag in argv:
            CFG[key] = argv[argv.index(flag) + 1]
    CFG["top"] = int(CFG["top"])
    if not CFG["owner"]:
        r = subprocess.run(["gh", "api", "user", "-q", ".login"], capture_output=True, text=True, check=True, **NO_WINDOW)
        CFG["owner"] = r.stdout.strip()


def main():
    global DATA
    configure(sys.argv[1:])
    DATA = HERE / Path(CFG["data"]).expanduser()
    today = dt.date.today()
    snapdir = DATA / "snapshots" / today.isoformat()
    snapdir.mkdir(parents=True, exist_ok=True)
    gsnap = github_snapshot()
    (snapdir / "github.json").write_text(json.dumps(gsnap, indent=1), encoding="utf-8")
    psnap = packages_snapshot(today)
    (snapdir / "packages.json").write_text(json.dumps(psnap, indent=1), encoding="utf-8")
    merge_daily_csv(gsnap)
    append_downloads_csv(psnap, gsnap, today.isoformat())
    summary = top_tables(gsnap, psnap, CFG["top"])
    (snapdir / "summary.md").write_text(f"# Repo traffic for {CFG['owner']}, {today}\n\n{summary}",
                                        encoding="utf-8")
    with (DATA / "run.log").open("a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.now().isoformat(timespec='seconds')} ok {len(gsnap)} repos, "
                f"{len(psnap['npm'])} npm, {len(psnap['nuget'])} nuget\n")
    print(summary)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        DATA.mkdir(parents=True, exist_ok=True)
        with (DATA / "run.log").open("a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now().isoformat(timespec='seconds')} FAILED {e!r}\n")
        raise
