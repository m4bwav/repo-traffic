"""The golden cases: invented accounts, repositories and packages, and the
gh and HTTP answers each run sees. Shapes follow the real APIs as read on
2026-10-08 (GitHub traffic, npm search and downloads, NuGet search and the
stats report). No name here belongs to a real account.

Each case is a dict:
  config   contents of repo_traffic.json next to the script, or None
  files    files that exist before the first run (path: text)
  runs     a list of runs, each with
             now    the fixed local clock (date.today, datetime.now)
             args   command-line arguments
             gh     the fake gh's answers (see fakegh.py)
             http   "host/path?query": list of responses, used in order,
                    the last one repeating; a response is
                    {"status": int, "json": obj} or {"status": int, "body": str}
             down   hosts whose connections fail
"""
import copy
import datetime

OWNER = "octo-example"
NPM_USER = "npm-example"
NUGET_OWNER = "nuget-example"
REPO_LIST = ("repo list %s --limit 1000 --json name,isPrivate,isFork,stargazerCount,forkCount" % OWNER)
NUGET_QUERY = "/query?take=1000&prerelease=true&semVerLevel=2.0.0&q=owner:" + NUGET_OWNER
USNC = "azuresearch-usnc.nuget.org"
USSC = "azuresearch-ussc.nuget.org"


def days(kind, start_day, counts):
    """A traffic answer: counts is a list of (count, uniques) from start_day on."""
    rows = [{"timestamp": "2026-%s-%02dT00:00:00Z" % (start_day[0], start_day[1] + i), "count": c, "uniques": u}
            for i, (c, u) in enumerate(counts)]
    return {"count": sum(c for c, _ in counts), "uniques": max([u for _, u in counts] or [0]), kind: rows}


REPOS = [
    {"name": "alpha-lib", "isPrivate": False, "isFork": False, "stargazerCount": 12, "forkCount": 3},
    {"name": "beta-tool", "isPrivate": False, "isFork": True, "stargazerCount": 0, "forkCount": 0},
    {"name": "gamma-private", "isPrivate": True, "isFork": False, "stargazerCount": 0, "forkCount": 0},
    {"name": "delta-empty", "isPrivate": False, "isFork": False, "stargazerCount": 1, "forkCount": 0},
]


def github(repos=REPOS, traffic=None, releases=None, no_access=()):
    traffic = traffic or {}
    releases = releases or {}
    gh = {REPO_LIST: {"json": repos}, "api user -q .login": {"stdout": OWNER + "\n"}}
    for r in repos:
        base = "api repos/%s/%s/" % (OWNER, r["name"])
        t = traffic.get(r["name"], {})
        gh[base + "releases?per_page=100"] = {"json": releases.get(r["name"], [])}
        for key, path in (("views", "traffic/views?per=day"), ("clones", "traffic/clones?per=day"),
                          ("referrers", "traffic/popular/referrers"), ("paths", "traffic/popular/paths")):
            if r["name"] in no_access:
                gh[base + path] = {"code": 1, "stderr": "gh: Must have push access to repository (HTTP 403)\n"}
            else:
                empty = {"count": 0, "uniques": 0, key: []} if key in ("views", "clones") else []
                gh[base + path] = {"json": t.get(key, empty)}
    return gh


TRAFFIC_1 = {
    "alpha-lib": {
        "views": days("views", ("09", 25), [(10, 4), (6, 3), (0, 0), (8, 5)]),
        "clones": days("clones", ("09", 26), [(3, 2), (5, 5)]),
        "referrers": [{"referrer": "github.com", "count": 10, "uniques": 4},
                      {"referrer": "news.example", "count": 3, "uniques": 2}],
        "paths": [{"path": "/octo-example/alpha-lib", "title": "alpha-lib", "count": 20, "uniques": 6}],
    },
    "beta-tool": {
        # Same unique cloners and clones as gamma-private: a tie in the summary.
        "views": days("views", ("10", 1), [(5, 5)]),
        "clones": days("clones", ("10", 2), [(2, 1)]),
    },
    "gamma-private": {
        "views": days("views", ("10", 6), [(7, 5), (1, 1)]),
        "clones": days("clones", ("10", 7), [(2, 1)]),
    },
}
RELEASES = {
    "alpha-lib": [{"tag_name": "v1.0.0", "assets": [{"name": "alpha-1.0.0.zip", "download_count": 7},
                                                    {"name": "alpha-1.0.0.tar.gz", "download_count": 2}]},
                  {"tag_name": "v0.9.0", "assets": []}],
    "delta-empty": [{"tag_name": "v0.1.0", "assets": [{"name": "delta.zip", "download_count": 0}]}],
}


def npm(start, end, packages):
    """packages: name -> (daily counts from start, last month)."""
    http = {"registry.npmjs.org/-/v1/search?size=250&text=maintainer:" + NPM_USER:
            [{"status": 200, "json": {"objects": [{"package": {"name": n}} for n in packages], "total": len(packages)}}]}
    first = datetime.date.fromisoformat(start)
    for name, (daily, month) in packages.items():
        rows = [{"downloads": c, "day": (first + datetime.timedelta(days=i)).isoformat()} for i, c in enumerate(daily)]
        http["api.npmjs.org/downloads/range/%s:%s/%s" % (start, end, name)] = [
            {"status": 200, "json": {"start": start, "end": end, "package": name, "downloads": rows}}]
        http["api.npmjs.org/downloads/point/last-month/" + name] = [
            {"status": 200, "json": {"downloads": month, "package": name}}]
    return http


def nuget_search(packages):
    """packages: id -> (total, {version: downloads})."""
    return {"totalHits": len(packages), "data": [
        {"id": pid, "totalDownloads": total, "versions": [{"version": v, "downloads": n} for v, n in vers.items()]}
        for pid, (total, vers) in packages.items()]}


def nuget_report(pid, facts):
    """facts: list of (version, client, amount)."""
    return {"Id": "report-Version", "Total": sum(a for _, _, a in facts), "Facts": [
        {"Dimensions": {"Version": v, "ClientName": c, "ClientVersion": "(unknown)", "Operation": "unknown"},
         "Amount": a} for v, c, a in facts]}


def nuget(usnc, ussc, reports):
    http = {USNC + NUGET_QUERY: [{"status": 200, "json": nuget_search(usnc)}],
            USSC + NUGET_QUERY: [{"status": 200, "json": nuget_search(ussc)}]}
    for pid, facts in reports.items():
        key = "www.nuget.org/stats/reports/packages/%s?groupby=Version" % pid
        http[key] = [{"status": 404, "body": "Not Found"}] if facts is None else [
            {"status": 200, "json": nuget_report(pid, facts)}]
    return http


NPM_1 = npm("2026-09-24", "2026-10-07", {
    "alpha-lib": ([1, 0, 4, 2, 0, 0, 3, 1, 1, 0, 2, 5, 0, 1], 40),
    "@octo-example/beta": ([0, 0, 1, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0], 3),
    "gamma-cli": ([1, 0, 4, 2, 0, 0, 3, 1, 1, 0, 2, 5, 0, 1], 41),
})
NUGET_1 = nuget(
    usnc={"Example.Core": (0, {"1.0.0": 0}), "Example.Tools": (3894, {"2.0.0": 3000, "1.0.0": 894})},
    ussc={"Example.Core": (183, {"1.0.0": 183}), "Example.Tools": (3923, {"2.0.0": 3020, "1.0.0": 903})},
    reports={"Example.Core": [("1.0.0", "NuGet Client", 150), ("1.0.0", "(unknown)", 49),
                              ("1.0.0-beta.1", "Go-http-client", 52)],
             "Example.Tools": [("2.0.0", "NuGet Client", 40), ("1.0.0", "NuGet Client", 2)]},
)
NOW_1 = "2026-10-08T09:00:00"
NOW_2 = "2026-10-21T09:00:00"
CONFIG = {"owner": OWNER, "npm_user": NPM_USER, "nuget_owner": NUGET_OWNER, "data": "data", "top": 10}


def run(now=NOW_1, args=(), gh=None, http=None, down=()):
    return {"now": now, "args": list(args), "gh": gh if gh is not None else github(traffic=TRAFFIC_1, releases=RELEASES),
            "http": http if http is not None else {**NPM_1, **NUGET_1}, "down": list(down)}


def with_http(changes):
    http = copy.deepcopy({**NPM_1, **NUGET_1})
    http.update(changes)
    return http


TRAFFIC_2 = copy.deepcopy(TRAFFIC_1)
# Thirteen days later: 2026-10-07 has its full count now, and new days follow.
TRAFFIC_2["gamma-private"]["views"] = days("views", ("10", 7), [(4, 3), (2, 2), (0, 0), (9, 6)])
TRAFFIC_2["alpha-lib"]["clones"] = days("clones", ("10", 15), [(1, 1)])
NPM_2 = npm("2026-10-07", "2026-10-20", {"alpha-lib": ([2] * 14, 50), "gamma-cli": ([0] * 14, 12)})

OLD_HEADER = "snapshot,registry,package,last_14_days,last_month,total\r\n2026-10-01,npm,alpha-lib,9,30,\r\n"

CASES = {
    "full": {"config": CONFIG, "files": {}, "runs": [run()]},
    "second-run-merges-daily": {"config": CONFIG, "files": {}, "runs": [
        run(), run(now=NOW_2, gh=github(traffic=TRAFFIC_2, releases=RELEASES), http={**NPM_2, **NUGET_1})]},
    "flags-no-config": {"config": None, "files": {}, "runs": [run(
        args=["--owner", OWNER, "--top", "1", "--data", "out/traffic"], http={})]},
    "owner-from-gh-login": {"config": None, "files": {}, "runs": [run(http={})]},
    "npm-only-flag-over-config": {"config": {**CONFIG, "nuget_owner": None}, "files": {}, "runs": [run(
        args=["--npm-user", NPM_USER], http=NPM_1)]},
    "no-push-access": {"config": CONFIG, "files": {}, "runs": [run(
        gh=github(traffic=TRAFFIC_1, releases=RELEASES, no_access=("gamma-private",)))]},
    "empty-account": {"config": CONFIG, "files": {}, "runs": [run(
        gh=github(repos=[]), http={**npm("2026-09-24", "2026-10-07", {}), **nuget({}, {}, {})})]},
    "npm-429-then-ok": {"config": CONFIG, "files": {}, "runs": [run(http=with_http({
        "api.npmjs.org/downloads/range/2026-09-24:2026-10-07/alpha-lib":
            [{"status": 429, "body": "Too Many Requests"}, {"status": 429, "body": "Too Many Requests"}]
            + NPM_1["api.npmjs.org/downloads/range/2026-09-24:2026-10-07/alpha-lib"]}))]},
    "npm-429-every-time": {"config": CONFIG, "files": {}, "runs": [run(http=with_http({
        "api.npmjs.org/downloads/range/2026-09-24:2026-10-07/alpha-lib": [{"status": 429, "body": "Too Many Requests"}]}))]},
    "npm-empty-body": {"config": CONFIG, "files": {}, "runs": [run(http=with_http({
        "api.npmjs.org/downloads/point/last-month/@octo-example/beta": [{"status": 200, "body": ""}]}))]},
    "npm-search-404": {"config": CONFIG, "files": {}, "runs": [run(http=with_http({
        "registry.npmjs.org/-/v1/search?size=250&text=maintainer:" + NPM_USER: [{"status": 404, "body": "Not Found"}]}))]},
    "nuget-replica-503": {"config": CONFIG, "files": {}, "runs": [run(http=with_http({
        USNC + NUGET_QUERY: [{"status": 503, "body": "Service Unavailable"}]}))]},
    "nuget-replica-unreachable": {"config": CONFIG, "files": {}, "runs": [run(down=[USSC])]},
    "nuget-stats-404": {"config": CONFIG, "files": {}, "runs": [run(http=with_http(nuget(
        usnc={"Example.Core": (0, {"1.0.0": 0})}, ussc={"Example.Core": (7, {"1.0.0": 7})},
        reports={"Example.Core": None})))]},
    "downloads-csv-old-header": {"config": CONFIG, "files": {"data/downloads.csv": OLD_HEADER}, "runs": [run()]},
    "help-flag-runs-a-snapshot": {"config": CONFIG, "files": {}, "runs": [run(args=["--help"])]},
    "top-without-value": {"config": CONFIG, "files": {}, "runs": [run(args=["--top"])]},
    "gh-login-fails-logs-to-default-data": {"config": None, "files": {}, "runs": [run(
        args=["--data", "elsewhere"], gh={REPO_LIST: {"json": []},
                                          "api user -q .login": {"code": 1, "stderr": "gh: not logged in\n"}},
        http={})]},
}
