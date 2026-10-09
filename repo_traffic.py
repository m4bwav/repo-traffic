"""Snapshot GitHub traffic and package downloads for every repo you own.

GitHub keeps traffic for 14 days only, so run this at least every 13 days.
Each run writes, under the data directory:

  snapshots/YYYY-MM-DD/github.json   per repo: daily views and clones,
                                     referrers, popular paths, stars, forks,
                                     release asset downloads
  snapshots/YYYY-MM-DD/packages.json npm daily downloads; NuGet downloads
                                     all time per version, and last 6
                                     weeks per version and client; PyPI
                                     downloads when packages are named
  snapshots/YYYY-MM-DD/summary.md    top-N tables for that run
  daily.csv      one row per repo per day, merged across runs
  downloads.csv  one row per package per run
  repos.csv      one row per repo per run: stars, forks, release downloads
  run.log        one line per run: ok, partial (a source failed) or FAILED

Needs Python 3.9+ and the gh CLI, logged in as an account with push access
to the repos (GitHub only shows traffic to those). Standard library only.
Settings come from repo_traffic.json (see repo_traffic.example.json) and
the flags, flags winning. Run as a file, the settings file and the data
folder sit next to this script; run as the repo-traffic command, in the
current folder. Exit status: 0 ok, 1 a source failed or the run failed,
2 bad arguments. Run with --help for the flags.
"""

import argparse
import csv
import datetime as dt
import json
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

__version__ = "1.0.0b1"

HERE = Path(__file__).resolve().parent
DEFAULTS = {"owner": None, "npm_user": None, "nuget_owner": None, "pypi_packages": [], "data": "data", "top": 10}
USER_AGENT = "repo-traffic"
NUGET_HOSTS = ("azuresearch-usnc", "azuresearch-ussc")
# Errors a source can fail with: network, HTTP, a cut-off body, a changed shape.
SOURCE_ERRORS = (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError)
# Keeps gh from flashing a console window when the scheduler runs pythonw.
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
DOWNLOADS_HEADER = ["snapshot", "registry", "package", "last_14_days", "last_month", "last_6_weeks", "total"]
# Headers written by earlier versions; a file with one is migrated once.
DOWNLOADS_OLD_HEADERS = [["snapshot", "registry", "package", "last_14_days", "last_month", "total"]]
REPOS_HEADER = ["snapshot", "repo", "private", "fork", "stars", "forks", "release_downloads"]


def describe(e):
    """A short reason for run.log and the summary."""
    if isinstance(e, urllib.error.HTTPError):
        return "HTTP %d" % e.code
    if isinstance(e, urllib.error.URLError):
        return "unreachable: %s" % (e.reason,)
    if isinstance(e, subprocess.CalledProcessError):
        return "gh exited %d" % e.returncode
    if isinstance(e, ValueError):
        return "bad response: %s" % e
    return "%s: %s" % (type(e).__name__, e)


def gh_call(args, check=False):
    """Run gh; return (stdout, stderr's first line or None when it succeeded)."""
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", **NO_WINDOW)
    if r.returncode != 0:
        if check:
            raise subprocess.CalledProcessError(r.returncode, ["gh", *args], output=r.stdout, stderr=r.stderr)
        lines = (r.stderr or "").strip().splitlines()
        return None, lines[0] if lines else "gh exited %d" % r.returncode
    return r.stdout, None


def gh(path):
    """gh api PATH as parsed JSON, or (None, the error) when gh refuses."""
    out, err = gh_call(["api", path])
    return (None, err) if err else (json.loads(out), None)


def gh_login():
    out, _ = gh_call(["api", "user", "-q", ".login"], check=True)
    return out.strip()


def retry_wait(e, attempt):
    try:
        return min(float(e.headers.get("Retry-After")), 120.0)
    except (TypeError, ValueError, AttributeError):
        return 10 * (attempt + 1)


def http_json(url, tries=5):
    """GET url as JSON; None on 404. Retries 429, empty bodies and dropped connections."""
    for i in range(tries):
        last = i == tries - 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as f:
                body = f.read()
            return json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429 and not last:
                time.sleep(retry_wait(e, i))
                continue
            raise
        except (urllib.error.URLError, socket.timeout, ConnectionError):
            if not last:
                time.sleep(5)
                continue
            raise
        except ValueError:
            # The npm stats API answers bursts with an empty body: wait as for a 429.
            if not last:
                time.sleep(10 * (i + 1))
                continue
            raise


def repos(owner):
    out, _ = gh_call(
        ["repo", "list", owner, "--limit", "1000", "--json", "name,isPrivate,isFork,stargazerCount,forkCount"],
        check=True,
    )
    return json.loads(out)


def github_snapshot(owner, failures):
    out = {}
    try:
        listed = repos(owner)
    except SOURCE_ERRORS as e:
        failures.append("github repo list (%s)" % describe(e))
        return out
    for repo in listed:
        full = "%s/%s" % (owner, repo["name"])
        releases, _ = gh("repos/%s/releases?per_page=100" % full)
        entry = {
            "private": repo["isPrivate"],
            "fork": repo["isFork"],
            "stars": repo["stargazerCount"],
            "forks": repo["forkCount"],
        }
        errors = []
        for key, path in (
            ("views", "traffic/views?per=day"),
            ("clones", "traffic/clones?per=day"),
            ("referrers", "traffic/popular/referrers"),
            ("paths", "traffic/popular/paths"),
        ):
            entry[key], err = gh("repos/%s/%s" % (full, path))
            if err:
                errors.append(err)
        entry["release_downloads"] = {
            rel["tag_name"]: {a["name"]: a["download_count"] for a in rel.get("assets", [])} for rel in releases or []
        }
        if errors:
            entry["traffic_error"] = errors[0]
        out[repo["name"]] = entry
    return out


def npm_snapshot(user, today, failures):
    npm = {}
    try:
        search = http_json("https://registry.npmjs.org/-/v1/search?size=250&text=maintainer:" + user)
        if search is None:
            failures.append("npm search (HTTP 404)")
            return npm
        names = [obj["package"]["name"] for obj in search["objects"]]
    except SOURCE_ERRORS as e:
        failures.append("npm search (%s)" % describe(e))
        return npm
    start = (today - dt.timedelta(days=14)).isoformat()
    end = (today - dt.timedelta(days=1)).isoformat()
    for name in names:
        try:
            rng = http_json("https://api.npmjs.org/downloads/range/%s:%s/%s" % (start, end, name)) or {}
            month = http_json("https://api.npmjs.org/downloads/point/last-month/" + name) or {}
            npm[name] = {"daily": rng.get("downloads", []), "last_month": month.get("downloads", 0)}
        except SOURCE_ERRORS as e:
            failures.append("npm %s (%s)" % (name, describe(e)))
        time.sleep(1)
    return npm


def nuget_snapshot(owner, failures, notes):
    # The two search replicas lag and disagree on all-time counts (on
    # 2026-10-08 one said 0 for a package nuget.org showed 251 for), so
    # take the higher. The stats report behind the package page's
    # "Full stats" covers the last 6 weeks, split by version and client.
    nuget, packages, down = {}, {}, []
    for host in NUGET_HOSTS:
        try:
            data = http_json(
                "https://%s.nuget.org/query?take=1000&prerelease=true&semVerLevel=2.0.0&q=owner:%s" % (host, owner)
            ) or {"data": []}
            for d in data["data"]:
                if d["totalDownloads"] >= packages.get(d["id"], {}).get("totalDownloads", -1):
                    packages[d["id"]] = d
        except SOURCE_ERRORS as e:
            down.append("%s (%s)" % (host, describe(e)))
    if len(down) == len(NUGET_HOSTS):
        failures.append("nuget search: " + ", ".join(down))
        return nuget
    if down:
        notes.append("nuget replica down: " + ", ".join(down))
    for pid, d in packages.items():
        try:
            try:
                report = http_json("https://www.nuget.org/stats/reports/packages/%s?groupby=Version" % pid) or {}
            except SOURCE_ERRORS as e:
                report = {}
                notes.append("nuget stats report %s (%s)" % (pid, describe(e)))
            versions, clients = {}, {}
            for fact in report.get("Facts", []):
                dims, n = fact["Dimensions"], fact["Amount"]
                versions[dims["Version"]] = versions.get(dims["Version"], 0) + n
                clients[dims["ClientName"]] = clients.get(dims["ClientName"], 0) + n
            nuget[pid] = {
                "total": max(d["totalDownloads"], report.get("Total") or 0),
                "versions": {v["version"]: v["downloads"] for v in d["versions"]},
                "last_6_weeks": report.get("Total"),
                "last_6_weeks_versions": versions,
                "last_6_weeks_clients": clients,
            }
        except SOURCE_ERRORS as e:
            failures.append("nuget %s (%s)" % (pid, describe(e)))
        time.sleep(1)
    return nuget


def pypi_snapshot(names, today, failures):
    # PyPI has no API that lists a user's projects, so the packages are named.
    pypi = {}
    start = (today - dt.timedelta(days=14)).isoformat()
    end = (today - dt.timedelta(days=1)).isoformat()
    for name in names:
        slug = re.sub(r"[-_.]+", "-", name).lower()
        try:
            recent = http_json("https://pypistats.org/api/packages/%s/recent" % slug)
            if recent is None:
                failures.append("pypi %s (HTTP 404: not on pypistats.org)" % name)
                time.sleep(1)
                continue
            overall = http_json("https://pypistats.org/api/packages/%s/overall?mirrors=false" % slug) or {}
            daily = [
                {"downloads": r["downloads"], "day": r["date"]}
                for r in overall.get("data", [])
                if r.get("category") == "without_mirrors" and start <= r["date"] <= end
            ]
            pypi[name] = {
                "daily": daily,
                "last_day": recent["data"]["last_day"],
                "last_week": recent["data"]["last_week"],
                "last_month": recent["data"]["last_month"],
            }
        except SOURCE_ERRORS as e:
            failures.append("pypi %s (%s)" % (name, describe(e)))
        time.sleep(1)
    return pypi


def merge_daily_csv(path, gsnap):
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


def open_csv_for_append(path, header, old_headers=()):
    """Open path to append rows under header: write the header to a new or
    empty file, migrate a file with an older header once (keeping NAME.bak),
    and refuse a file whose header is unknown."""
    if path.exists() and path.stat().st_size:
        with path.open(newline="", encoding="utf-8") as f:
            first = next(csv.reader(f), [])
        if first in old_headers:
            shutil.copyfile(path, path.with_name(path.name + ".bak"))
            with path.open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(header)
                w.writerows([r.get(k, "") for k in header] for r in rows)
        elif first != header:
            raise ValueError("%s has an unknown header, so no rows were added: %s" % (path.name, ",".join(first)))
        f = path.open("a", newline="", encoding="utf-8")
        return f, csv.writer(f)
    f = path.open("w", newline="", encoding="utf-8")
    w = csv.writer(f)
    w.writerow(header)
    return f, w


def release_total(d):
    return sum(sum(a.values()) for a in d["release_downloads"].values())


def append_downloads_csv(path, psnap, gsnap, today):
    f, w = open_csv_for_append(path, DOWNLOADS_HEADER, DOWNLOADS_OLD_HEADERS)
    with f:
        for name, d in psnap["npm"].items():
            w.writerow([today, "npm", name, sum(x["downloads"] for x in d["daily"]), d["last_month"], "", ""])
        for name, d in psnap["nuget"].items():
            w.writerow([today, "nuget", name, "", "", d["last_6_weeks"], d["total"]])
        for name, d in psnap.get("pypi", {}).items():
            w.writerow([today, "pypi", name, sum(x["downloads"] for x in d["daily"]), d["last_month"], "", ""])
        for name, d in gsnap.items():
            if release_total(d):
                w.writerow([today, "github-release", name, "", "", "", release_total(d)])


def append_repos_csv(path, gsnap, today):
    f, w = open_csv_for_append(path, REPOS_HEADER)
    with f:
        for name, d in gsnap.items():
            w.writerow(
                [
                    today,
                    name,
                    str(d["private"]).lower(),
                    str(d["fork"]).lower(),
                    d["stars"],
                    d["forks"],
                    release_total(d),
                ]
            )


def top_tables(gsnap, psnap, n):
    def u(d, k):
        return (d[k] or {}).get("uniques", 0), (d[k] or {}).get("count", 0)

    def daily_sum(d):
        return sum(x["downloads"] for x in d["daily"])

    # Every table breaks ties by name last, so equal counts list the same way every run.
    tables = [
        (
            "Unique cloners, last 14 days",
            ["Repo", "Unique cloners", "Clones"],
            sorted(((k, *u(d, "clones")) for k, d in gsnap.items()), key=lambda r: (-r[1], -r[2], r[0])),
        ),
        (
            "Unique visitors, last 14 days",
            ["Repo", "Unique visitors", "Views"],
            sorted(((k, *u(d, "views")) for k, d in gsnap.items()), key=lambda r: (-r[1], -r[2], r[0])),
        ),
        (
            "npm downloads",
            ["Package", "Last 14 days", "Last month"],
            sorted(((k, daily_sum(d), d["last_month"]) for k, d in psnap["npm"].items()), key=lambda r: (-r[1], r[0])),
        ),
        (
            "NuGet downloads",
            ["Package", "Last 6 weeks", "All time"],
            sorted(
                ((k, d["last_6_weeks"] or 0, d["total"]) for k, d in psnap["nuget"].items()),
                key=lambda r: (-r[1], -r[2], r[0]),
            ),
        ),
        (
            "PyPI downloads",
            ["Package", "Last 14 days", "Last month"],
            sorted(
                ((k, daily_sum(d), d["last_month"]) for k, d in psnap.get("pypi", {}).items()),
                key=lambda r: (-r[1], r[0]),
            ),
        ),
        (
            "GitHub release asset downloads, all time",
            ["Repo", "Downloads"],
            sorted(((k, release_total(d)) for k, d in gsnap.items() if release_total(d)), key=lambda r: (-r[1], r[0])),
        ),
    ]
    out = []
    for title, head, rows in tables:
        if not rows:
            continue
        out += ["## %s" % title, "", "| # | " + " | ".join(head) + " |", "|---|" + "---|" * len(head)]
        out += [
            "| %d | " % i + " | ".join(f"{x:,}" if isinstance(x, int) else str(x) for x in r) + " |"
            for i, r in enumerate(rows[:n], 1)
        ]
        out.append("")
    return "\n".join(out)


def gap_warning(log_path, today):
    """A warning when the last complete run is more than 14 days old: GitHub
    has dropped the traffic in between."""
    last = None
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            parts = line.split(" ", 2)
            if len(parts) > 1 and parts[1] == "ok":
                try:
                    last = dt.datetime.fromisoformat(parts[0]).date()
                except ValueError:
                    pass
    if last is None or (today - last).days <= 14:
        return None
    return "gap: %d days since the last complete run (%s); GitHub traffic from before %s was not saved" % (
        (today - last).days,
        last,
        today - dt.timedelta(days=14),
    )


def write_log(data, text):
    data.mkdir(parents=True, exist_ok=True)
    with (data / "run.log").open("a", encoding="utf-8") as f:
        f.write("%s %s\n" % (dt.datetime.now().isoformat(timespec="seconds"), text))


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="repo-traffic",
        description="Save GitHub traffic and npm, NuGet and PyPI download counts before GitHub's 14 days run out.",
        add_help=False,
    )
    # A named group, so --help reads the same on every Python (3.9 titles the default group "optional arguments").
    p = parser.add_argument_group("options")
    p.add_argument("-h", "--help", action="help", help="show this help message and exit")
    p.add_argument("--owner", help="GitHub owner whose repos to read (default: the gh login)")
    p.add_argument("--npm-user", help="npm username whose packages to count (default: npm skipped)")
    p.add_argument("--nuget-owner", help="nuget.org owner whose packages to count (default: NuGet skipped)")
    p.add_argument("--pypi-packages", help="comma-separated PyPI project names to count (default: PyPI skipped)")
    p.add_argument("--data", help="data folder, relative to the settings folder (default: data)")
    p.add_argument("--top", type=int, help="rows per summary table (default: 10)")
    p.add_argument("--config", help="settings file (default: repo_traffic.json in the settings folder)")
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    return parser.parse_args(argv)


def configure(args, base):
    cfg = dict(DEFAULTS)
    path = Path(args.config).expanduser() if args.config else base / "repo_traffic.json"
    if args.config or path.exists():
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
    for key in ("owner", "npm_user", "nuget_owner", "data", "top"):
        if getattr(args, key) is not None:
            cfg[key] = getattr(args, key)
    if args.pypi_packages is not None:
        cfg["pypi_packages"] = [x.strip() for x in args.pypi_packages.split(",") if x.strip()]
    cfg["top"] = int(cfg["top"])
    return cfg


def snapshot(cfg, data, today):
    failures, notes = [], []
    owner = cfg["owner"] or gh_login()
    snapdir = data / "snapshots" / today.isoformat()
    snapdir.mkdir(parents=True, exist_ok=True)
    gap = gap_warning(data / "run.log", today)
    gsnap = github_snapshot(owner, failures)
    (snapdir / "github.json").write_text(json.dumps(gsnap, indent=1), encoding="utf-8")
    psnap = {
        "npm": npm_snapshot(cfg["npm_user"], today, failures) if cfg["npm_user"] else {},
        "nuget": nuget_snapshot(cfg["nuget_owner"], failures, notes) if cfg["nuget_owner"] else {},
    }
    if cfg["pypi_packages"]:
        psnap["pypi"] = pypi_snapshot(cfg["pypi_packages"], today, failures)
    (snapdir / "packages.json").write_text(json.dumps(psnap, indent=1), encoding="utf-8")
    merge_daily_csv(data / "daily.csv", gsnap)
    for name, write in (
        ("downloads.csv", lambda p: append_downloads_csv(p, psnap, gsnap, today.isoformat())),
        ("repos.csv", lambda p: append_repos_csv(p, gsnap, today.isoformat())),
    ):
        try:
            write(data / name)
        except ValueError as e:
            failures.append(str(e))
    summary = top_tables(gsnap, psnap, cfg["top"])
    no_access = [k for k, d in gsnap.items() if d.get("traffic_error")]
    if no_access:
        summary += ("\n" if summary else "") + (
            "## No traffic access\n\nGitHub refused traffic for %s (it needs push access): %s\n"
            % ("this repo" if len(no_access) == 1 else "these repos", ", ".join(no_access))
        )
    if failures:
        summary += ("\n" if summary else "") + "## Not counted this run\n\n" + "".join("- %s\n" % x for x in failures)
    head = "# Repo traffic for %s, %s\n\n" % (owner, today) + ("> %s\n\n" % gap if gap else "")
    (snapdir / "summary.md").write_text(head + summary, encoding="utf-8")
    counts = "%d repos, %d npm, %d nuget" % (len(gsnap), len(psnap["npm"]), len(psnap["nuget"]))
    if "pypi" in psnap:
        counts += ", %d pypi" % len(psnap["pypi"])
    extra = ["failed: " + "; ".join(failures)] if failures else []
    extra += ["no traffic access: " + ", ".join(no_access)] if no_access else []
    extra += notes
    if gap:
        write_log(data, gap)
    write_log(data, "%s %s" % ("partial" if failures else "ok", "; ".join([counts] + extra)))
    if gap:
        print(gap)
    print(summary)
    if failures:
        print("repo-traffic: some sources failed, see run.log: " + "; ".join(failures), file=sys.stderr)
        return 1
    return 0


def main(argv=None, base=None):
    """Run one snapshot. base is the settings folder (default: the current folder)."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    base = Path(base) if base is not None else Path.cwd()
    data = base / "data"
    try:
        cfg = configure(args, base)
        data = base / Path(cfg["data"]).expanduser()
        return snapshot(cfg, data, dt.date.today())
    except Exception as e:
        write_log(data, "FAILED %r" % (e,))
        raise


def cli():
    """The repo-traffic command: settings and data in the current folder."""
    sys.exit(main())


if __name__ == "__main__":
    sys.exit(main(base=HERE))
