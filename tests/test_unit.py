"""Unit tests for every function in repo_traffic.py, with gh, HTTP and sleep
faked in process. Nothing here leaves the machine."""

import datetime as dt
import io
import json
import subprocess
import sys
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import repo_traffic as rt  # noqa: E402

TODAY = dt.date(2026, 10, 8)


# ---------------------------------------------------------------- fakes


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def http_error(code, headers=None):
    msg = Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return urllib.error.HTTPError("https://x.example/", code, "error %d" % code, msg, io.BytesIO(b""))


@pytest.fixture
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(rt.time, "sleep", calls.append)
    return calls


@pytest.fixture
def web(monkeypatch, sleeps):
    """urls: url -> list of answers (bytes, an exception, or a JSON-able object), used in order."""
    answers = {}

    def urlopen(req, timeout=None):
        url = req.full_url
        assert req.get_header("User-agent") == "repo-traffic"
        queue = answers.get(url)
        if not queue:
            raise http_error(404)
        a = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(a, BaseException):
            raise a
        return FakeResponse(a if isinstance(a, bytes) else json.dumps(a).encode())

    monkeypatch.setattr(rt.urllib.request, "urlopen", urlopen)
    return answers


@pytest.fixture
def fake_gh(monkeypatch):
    """answers: tuple(args) -> (code, stdout, stderr)."""
    answers, calls = {}, []

    def run(cmd, **kw):
        assert cmd[0] == "gh"
        calls.append(tuple(cmd[1:]))
        code, out, err = answers.get(tuple(cmd[1:]), (1, "", "no fixture\n"))
        return subprocess.CompletedProcess(cmd, code, out, err)

    monkeypatch.setattr(rt.subprocess, "run", run)
    answers["calls"] = calls
    return answers


def traffic(kind, rows):
    return {
        "count": sum(c for _, c, _ in rows),
        "uniques": max([u for _, _, u in rows] or [0]),
        kind: [{"timestamp": d + "T00:00:00Z", "count": c, "uniques": u} for d, c, u in rows],
    }


# ---------------------------------------------------------------- describe, gh


def test_describe_each_kind():
    assert rt.describe(http_error(503)) == "HTTP 503"
    assert rt.describe(urllib.error.URLError("refused")) == "unreachable: refused"
    assert rt.describe(subprocess.CalledProcessError(4, ["gh"])) == "gh exited 4"
    assert rt.describe(ValueError("empty")) == "bad response: empty"
    assert rt.describe(KeyError("Facts")) == "KeyError: 'Facts'"


def test_gh_call_success_failure_and_check(fake_gh):
    fake_gh[("api", "ok")] = (0, '{"a": 1}', "")
    fake_gh[("api", "no")] = (1, "", "gh: Must have push access (HTTP 403)\nmore\n")
    fake_gh[("api", "silent")] = (2, "", "")
    assert rt.gh("ok") == ({"a": 1}, None)
    assert rt.gh("no") == (None, "gh: Must have push access (HTTP 403)")
    assert rt.gh_call(["api", "silent"]) == (None, "gh exited 2")
    with pytest.raises(subprocess.CalledProcessError) as e:
        rt.gh_call(["api", "no"], check=True)
    assert repr(e.value) == "CalledProcessError(1, ['gh', 'api', 'no'])"


def test_gh_login_strips(fake_gh):
    fake_gh[("api", "user", "-q", ".login")] = (0, "octo-example\n", "")
    assert rt.gh_login() == "octo-example"


def test_gh_runs_without_a_console_window_on_windows():
    if sys.platform == "win32":
        assert rt.NO_WINDOW == {"creationflags": subprocess.CREATE_NO_WINDOW}
    else:
        assert rt.NO_WINDOW == {}


def test_repos_reads_the_list(fake_gh):
    args = ("repo", "list", "o", "--limit", "1000", "--json", "name,isPrivate,isFork,stargazerCount,forkCount")
    fake_gh[args] = (0, '[{"name": "r"}]', "")
    assert rt.repos("o") == [{"name": "r"}]


# ---------------------------------------------------------------- http_json


def test_retry_wait_uses_retry_after_capped():
    assert rt.retry_wait(http_error(429, {"Retry-After": "3"}), 0) == 3.0
    assert rt.retry_wait(http_error(429, {"Retry-After": "9999"}), 0) == 120.0
    assert rt.retry_wait(http_error(429, {"Retry-After": "Wed, 21 Oct 2026"}), 1) == 20
    assert rt.retry_wait(http_error(429), 2) == 30


def test_http_json_ok_and_404(web):
    web["https://a/"] = [{"x": 1}]
    assert rt.http_json("https://a/") == {"x": 1}
    assert rt.http_json("https://missing/") is None


def test_http_json_429_then_ok(web, sleeps):
    web["https://a/"] = [http_error(429), http_error(429, {"Retry-After": "2"}), {"ok": True}]
    assert rt.http_json("https://a/") == {"ok": True}
    assert sleeps == [10, 2.0]


def test_http_json_429_exhausted_raises(web, sleeps):
    web["https://a/"] = [http_error(429)]
    with pytest.raises(urllib.error.HTTPError):
        rt.http_json("https://a/", tries=3)
    assert sleeps == [10, 20]


def test_http_json_other_status_raises_at_once(web, sleeps):
    web["https://a/"] = [http_error(500)]
    with pytest.raises(urllib.error.HTTPError):
        rt.http_json("https://a/")
    assert sleeps == []


def test_http_json_unreachable_retries_then_raises(web, sleeps):
    web["https://a/"] = [urllib.error.URLError("down")]
    with pytest.raises(urllib.error.URLError):
        rt.http_json("https://a/", tries=3)
    assert sleeps == [5, 5]


def test_http_json_timeout_retries(web, sleeps):
    web["https://a/"] = [rt.socket.timeout("slow"), {"ok": 1}]
    assert rt.http_json("https://a/") == {"ok": 1}
    assert sleeps == [5]


def test_http_json_empty_body_retries_then_raises(web, sleeps):
    web["https://a/"] = [b"", b"{}"]
    assert rt.http_json("https://a/") == {}
    web["https://b/"] = [b""]
    with pytest.raises(ValueError):
        rt.http_json("https://b/", tries=2)
    assert sleeps == [10, 10]


# ---------------------------------------------------------------- github


REPO_LIST = ("repo", "list", "o", "--limit", "1000", "--json", "name,isPrivate,isFork,stargazerCount,forkCount")


def test_github_snapshot_repo_list_failure(fake_gh):
    failures = []
    assert rt.github_snapshot("o", failures) == {}
    assert failures == ["github repo list (gh exited 1)"]


def test_github_snapshot_entry_and_traffic_error(fake_gh):
    fake_gh[REPO_LIST] = (
        0,
        json.dumps([{"name": "r", "isPrivate": True, "isFork": False, "stargazerCount": 2, "forkCount": 1}]),
        "",
    )
    fake_gh[("api", "repos/o/r/releases?per_page=100")] = (
        0,
        json.dumps([{"tag_name": "v1", "assets": [{"name": "a.zip", "download_count": 4}]}, {"tag_name": "v0"}]),
        "",
    )
    fake_gh[("api", "repos/o/r/traffic/views?per=day")] = (1, "", "gh: Must have push access (HTTP 403)\n")
    fake_gh[("api", "repos/o/r/traffic/clones?per=day")] = (1, "", "gh: Must have push access (HTTP 403)\n")
    fake_gh[("api", "repos/o/r/traffic/popular/referrers")] = (0, "[]", "")
    fake_gh[("api", "repos/o/r/traffic/popular/paths")] = (0, "[]", "")
    failures = []
    snap = rt.github_snapshot("o", failures)
    assert failures == []
    assert list(snap["r"]) == [
        "private",
        "fork",
        "stars",
        "forks",
        "views",
        "clones",
        "referrers",
        "paths",
        "release_downloads",
        "traffic_error",
    ]
    assert snap["r"]["views"] is None
    assert snap["r"]["release_downloads"] == {"v1": {"a.zip": 4}, "v0": {}}
    assert snap["r"]["traffic_error"] == "gh: Must have push access (HTTP 403)"


def test_github_snapshot_missing_releases_is_empty(fake_gh):
    fake_gh[REPO_LIST] = (
        0,
        json.dumps([{"name": "r", "isPrivate": False, "isFork": False, "stargazerCount": 0, "forkCount": 0}]),
        "",
    )
    for p in ("traffic/views?per=day", "traffic/clones?per=day", "traffic/popular/referrers", "traffic/popular/paths"):
        fake_gh[("api", "repos/o/r/" + p)] = (0, "null", "")
    snap = rt.github_snapshot("o", [])
    assert snap["r"]["release_downloads"] == {}
    assert "traffic_error" not in snap["r"]


# ---------------------------------------------------------------- npm, nuget, pypi

SEARCH = "https://registry.npmjs.org/-/v1/search?size=250&text=maintainer:u"


def test_npm_snapshot_dates_and_values(web, sleeps):
    web[SEARCH] = [{"objects": [{"package": {"name": "p"}}]}]
    web["https://api.npmjs.org/downloads/range/2026-09-24:2026-10-07/p"] = [
        {"downloads": [{"day": "d", "downloads": 3}]}
    ]
    web["https://api.npmjs.org/downloads/point/last-month/p"] = [{"downloads": 9}]
    failures = []
    assert rt.npm_snapshot("u", TODAY, failures) == {"p": {"daily": [{"day": "d", "downloads": 3}], "last_month": 9}}
    assert failures == [] and sleeps == [1]


def test_npm_snapshot_missing_stats_default_to_zero(web, sleeps):
    web[SEARCH] = [{"objects": [{"package": {"name": "p"}}]}]
    assert rt.npm_snapshot("u", TODAY, []) == {"p": {"daily": [], "last_month": 0}}


def test_npm_snapshot_search_404_and_error(web, sleeps):
    failures = []
    assert rt.npm_snapshot("u", TODAY, failures) == {}
    web[SEARCH] = [http_error(500)]
    assert rt.npm_snapshot("u", TODAY, failures) == {}
    web[SEARCH] = [{"no objects": []}]
    assert rt.npm_snapshot("u", TODAY, failures) == {}
    assert failures == ["npm search (HTTP 404)", "npm search (HTTP 500)", "npm search (KeyError: 'objects')"]


def test_npm_snapshot_one_package_fails_others_kept(web, sleeps):
    web[SEARCH] = [{"objects": [{"package": {"name": "bad"}}, {"package": {"name": "good"}}]}]
    web["https://api.npmjs.org/downloads/range/2026-09-24:2026-10-07/bad"] = [http_error(500)]
    web["https://api.npmjs.org/downloads/point/last-month/good"] = [{"downloads": 1}]
    failures = []
    assert rt.npm_snapshot("u", TODAY, failures) == {"good": {"daily": [], "last_month": 1}}
    assert failures == ["npm bad (HTTP 500)"]
    assert sleeps == [1, 1]


Q = "/query?take=1000&prerelease=true&semVerLevel=2.0.0&q=owner:n"
USNC, USSC = "https://azuresearch-usnc.nuget.org" + Q, "https://azuresearch-ussc.nuget.org" + Q
STATS = "https://www.nuget.org/stats/reports/packages/%s?groupby=Version"


def search(*pkgs):
    return {
        "data": [{"id": i, "totalDownloads": t, "versions": [{"version": "1.0.0", "downloads": t}]} for i, t in pkgs]
    }


def test_nuget_takes_the_highest_replica_and_the_report(web, sleeps):
    web[USNC] = [search(("A", 0), ("B", 10))]
    web[USSC] = [search(("A", 5), ("B", 8))]
    web[STATS % "A"] = [
        {
            "Total": 7,
            "Facts": [
                {"Dimensions": {"Version": "1.0.0", "ClientName": "c1"}, "Amount": 4},
                {"Dimensions": {"Version": "1.0.0", "ClientName": "c2"}, "Amount": 3},
            ],
        }
    ]
    failures, notes = [], []
    out = rt.nuget_snapshot("n", failures, notes)
    assert out["A"] == {
        "total": 7,
        "versions": {"1.0.0": 5},
        "last_6_weeks": 7,
        "last_6_weeks_versions": {"1.0.0": 7},
        "last_6_weeks_clients": {"c1": 4, "c2": 3},
    }
    assert out["B"]["total"] == 10 and out["B"]["last_6_weeks"] is None
    assert failures == [] and notes == [] and sleeps == [1, 1]


def test_nuget_one_replica_down_is_a_note(web, sleeps):
    web[USNC] = [http_error(503)]
    web[USSC] = [search(("A", 5))]
    failures, notes = [], []
    assert list(rt.nuget_snapshot("n", failures, notes)) == ["A"]
    assert failures == [] and notes == ["nuget replica down: azuresearch-usnc (HTTP 503)"]


def test_nuget_both_replicas_down_is_a_failure(web, sleeps):
    web[USNC] = [http_error(503)]
    web[USSC] = [http_error(502)]
    failures = []
    assert rt.nuget_snapshot("n", failures, []) == {}
    assert failures == ["nuget search: azuresearch-usnc (HTTP 503), azuresearch-ussc (HTTP 502)"]


def test_nuget_stats_report_error_is_a_note(web, sleeps):
    web[USNC] = web[USSC] = [search(("A", 5))]
    web[STATS % "A"] = [http_error(500)]
    notes = []
    out = rt.nuget_snapshot("n", [], notes)
    assert out["A"]["total"] == 5 and out["A"]["last_6_weeks"] is None
    assert notes == ["nuget stats report A (HTTP 500)"]


def test_nuget_odd_report_shape_fails_that_package(web, sleeps):
    web[USNC] = web[USSC] = [search(("A", 5))]
    web[STATS % "A"] = [{"Total": 1, "Facts": [{"Amount": 1}]}]
    failures = []
    assert rt.nuget_snapshot("n", failures, []) == {}
    assert failures == ["nuget A (KeyError: 'Dimensions')"]


def test_pypi_snapshot_filters_days_and_mirrors(web, sleeps):
    base = "https://pypistats.org/api/packages/my-pkg/"
    web[base + "recent"] = [{"data": {"last_day": 1, "last_week": 5, "last_month": 20}}]
    web[base + "overall?mirrors=false"] = [
        {
            "data": [
                {"category": "without_mirrors", "date": "2026-09-23", "downloads": 100},
                {"category": "without_mirrors", "date": "2026-09-24", "downloads": 2},
                {"category": "with_mirrors", "date": "2026-09-24", "downloads": 50},
                {"category": "without_mirrors", "date": "2026-10-07", "downloads": 3},
                {"category": "without_mirrors", "date": "2026-10-08", "downloads": 9},
            ]
        }
    ]
    failures = []
    out = rt.pypi_snapshot(["My_Pkg"], TODAY, failures)
    assert out == {
        "My_Pkg": {
            "daily": [{"downloads": 2, "day": "2026-09-24"}, {"downloads": 3, "day": "2026-10-07"}],
            "last_day": 1,
            "last_week": 5,
            "last_month": 20,
        }
    }
    assert failures == [] and sleeps == [1]


def test_pypi_snapshot_404_and_error(web, sleeps):
    web["https://pypistats.org/api/packages/b/recent"] = [http_error(500)]
    failures = []
    assert rt.pypi_snapshot(["a", "b"], TODAY, failures) == {}
    assert failures == ["pypi a (HTTP 404: not on pypistats.org)", "pypi b (HTTP 500)"]
    assert sleeps == [1, 1]


# ---------------------------------------------------------------- CSVs


def test_merge_daily_csv_new_then_merged(tmp_path):
    path = tmp_path / "daily.csv"
    g1 = {"r": {"views": traffic("views", [("2026-10-01", 3, 2)]), "clones": None}}
    rt.merge_daily_csv(path, g1)
    assert path.read_bytes() == b"repo,date,views,views_uniques,clones,clones_uniques\r\nr,2026-10-01,3,2,0,0\r\n"
    g2 = {
        "r": {
            "views": traffic("views", [("2026-10-01", 5, 4), ("2026-10-02", 1, 1)]),
            "clones": traffic("clones", [("2026-10-01", 2, 1)]),
        },
        "a": {"views": None, "clones": None},
    }
    rt.merge_daily_csv(path, g2)
    assert path.read_text(encoding="utf-8").splitlines() == [
        "repo,date,views,views_uniques,clones,clones_uniques",
        "r,2026-10-01,5,4,2,1",
        "r,2026-10-02,1,1,0,0",
    ]


def test_open_csv_for_append_new_and_empty_file(tmp_path):
    for existing in (None, b""):
        path = tmp_path / "x.csv"
        if existing is not None:
            path.write_bytes(existing)
        f, w = rt.open_csv_for_append(path, ["a", "b"])
        with f:
            w.writerow([1, 2])
        assert path.read_bytes() == b"a,b\r\n1,2\r\n"
        path.unlink()


def test_open_csv_for_append_current_header_appends(tmp_path):
    path = tmp_path / "x.csv"
    path.write_bytes(b"a,b\r\n1,2\r\n")
    f, w = rt.open_csv_for_append(path, ["a", "b"], [["a"]])
    with f:
        w.writerow([3, 4])
    assert path.read_bytes() == b"a,b\r\n1,2\r\n3,4\r\n"
    assert not (tmp_path / "x.csv.bak").exists()


def test_open_csv_for_append_migrates_an_old_header(tmp_path):
    path = tmp_path / "downloads.csv"
    old = b"snapshot,registry,package,last_14_days,last_month,total\r\n2026-10-01,npm,p,9,30,\r\n"
    path.write_bytes(old)
    f, w = rt.open_csv_for_append(path, rt.DOWNLOADS_HEADER, rt.DOWNLOADS_OLD_HEADERS)
    with f:
        w.writerow(["2026-10-08", "nuget", "q", "", "", 5, 6])
    assert (tmp_path / "downloads.csv.bak").read_bytes() == old
    assert path.read_text(encoding="utf-8").splitlines() == [
        ",".join(rt.DOWNLOADS_HEADER),
        "2026-10-01,npm,p,9,30,,",
        "2026-10-08,nuget,q,,,5,6",
    ]


def test_open_csv_for_append_refuses_an_unknown_header(tmp_path):
    path = tmp_path / "x.csv"
    path.write_bytes(b"what,is,this\r\n")
    with pytest.raises(ValueError, match="x.csv has an unknown header"):
        rt.open_csv_for_append(path, ["a", "b"])
    assert path.read_bytes() == b"what,is,this\r\n"


def gsnap_one(release=0):
    return {
        "r": {
            "private": True,
            "fork": False,
            "stars": 3,
            "forks": 1,
            "views": None,
            "clones": None,
            "release_downloads": {"v1": {"a": release}} if release else {},
        }
    }


def test_append_downloads_csv_every_registry(tmp_path):
    path = tmp_path / "downloads.csv"
    psnap = {
        "npm": {"n": {"daily": [{"downloads": 2}, {"downloads": 3}], "last_month": 9}},
        "nuget": {"g": {"last_6_weeks": None, "total": 4}},
        "pypi": {"p": {"daily": [{"downloads": 1}], "last_month": 7}},
    }
    rt.append_downloads_csv(path, psnap, gsnap_one(release=5), "2026-10-08")
    assert path.read_text(encoding="utf-8").splitlines()[1:] == [
        "2026-10-08,npm,n,5,9,,",
        "2026-10-08,nuget,g,,,,4",
        "2026-10-08,pypi,p,1,7,,",
        "2026-10-08,github-release,r,,,,5",
    ]


def test_append_repos_csv(tmp_path):
    path = tmp_path / "repos.csv"
    rt.append_repos_csv(path, gsnap_one(release=2), "2026-10-08")
    assert path.read_text(encoding="utf-8").splitlines() == [",".join(rt.REPOS_HEADER), "2026-10-08,r,true,false,3,1,2"]


# ---------------------------------------------------------------- summary, gap, log


def test_top_tables_break_ties_by_name_and_cut_at_n():
    g = {n: {"views": {"uniques": 1, "count": 1}, "clones": None, "release_downloads": {}} for n in ("c", "a", "b")}
    p = {
        "npm": {"z": {"daily": [], "last_month": 0}, "y": {"daily": [], "last_month": 5}},
        "nuget": {},
        "pypi": {"q": {"daily": [{"downloads": 4}], "last_month": 4}},
    }
    out = rt.top_tables(g, p, 2)
    assert "| 1 | a | 1 | 1 |\n| 2 | b | 1 | 1 |\n\n" in out
    assert "| 1 | y | 0 | 5 |\n| 2 | z | 0 | 0 |" in out
    assert "## PyPI downloads" in out and "| 1 | q | 4 | 4 |" in out
    assert "NuGet" not in out and "| 3 |" not in out


def test_top_tables_empty():
    assert rt.top_tables({}, {"npm": {}, "nuget": {}}, 10) == ""


def test_gap_warning(tmp_path):
    log = tmp_path / "run.log"
    assert rt.gap_warning(log, TODAY) is None
    log.write_text("garbage\n2026-09-01T09:00:00 FAILED x\nnot-a-date ok 1\n", encoding="utf-8")
    assert rt.gap_warning(log, TODAY) is None
    log.write_text(
        "2026-09-20T09:00:00 ok 1 repos\n2026-09-30T09:00:00 partial 0 repos; failed: github repo list (gh exited 1)\n",
        encoding="utf-8",
    )
    assert rt.gap_warning(log, TODAY) == (
        "gap: 18 days since the last run that saved GitHub traffic (2026-09-20); "
        "traffic from before 2026-09-24 was not saved"
    )
    log.write_text("2026-09-24T09:00:00 ok 1 repos\n", encoding="utf-8")
    assert rt.gap_warning(log, TODAY) is None


def test_gap_warning_counts_partial_runs_that_saved_github(tmp_path):
    # Review finding 2: a run where only npm failed still saved GitHub traffic.
    log = tmp_path / "run.log"
    log.write_text(
        "2026-09-01T09:00:00 ok 1 repos\n"
        "2026-09-14T09:00:00 partial 4 repos, 0 npm; failed: npm search (HTTP 404)\n"
        "2026-09-27T09:00:00 partial 4 repos, 0 npm; failed: npm search (HTTP 404)\n",
        encoding="utf-8",
    )
    assert rt.gap_warning(log, TODAY) is None


def test_write_log_creates_the_folder(tmp_path, monkeypatch):
    rt.write_log(tmp_path / "new" / "data", "ok x")
    line = (tmp_path / "new" / "data" / "run.log").read_text(encoding="utf-8")
    assert line.endswith(" ok x\n") and line[:4].isdigit()


# ---------------------------------------------------------------- arguments and settings


def test_parse_args_version_and_errors(capsys):
    with pytest.raises(SystemExit) as e:
        rt.parse_args(["--version"])
    assert e.value.code == 0 and capsys.readouterr().out.strip() == "repo-traffic " + rt.__version__
    for bad in (["--top"], ["--top", "x"], ["--nope"]):
        with pytest.raises(SystemExit) as e:
            rt.parse_args(bad)
        assert e.value.code == 2


def test_configure_file_flags_and_defaults(tmp_path):
    (tmp_path / "repo_traffic.json").write_text(
        json.dumps({"owner": "o", "top": "3", "npm_user": "u"}), encoding="utf-8"
    )
    cfg = rt.configure(rt.parse_args(["--npm-user", "v", "--pypi-packages", " a, ,b "]), tmp_path)
    assert cfg == {
        "owner": "o",
        "npm_user": "v",
        "nuget_owner": None,
        "pypi_packages": ["a", "b"],
        "data": "data",
        "top": 3,
    }
    assert rt.configure(rt.parse_args([]), tmp_path / "none") == rt.DEFAULTS


def test_configure_explicit_config_path(tmp_path):
    other = tmp_path / "elsewhere.json"
    other.write_text(json.dumps({"owner": "x", "pypi_packages": ["p"]}), encoding="utf-8")
    cfg = rt.configure(rt.parse_args(["--config", str(other)]), tmp_path)
    assert cfg["owner"] == "x" and cfg["pypi_packages"] == ["p"]
    with pytest.raises(FileNotFoundError):
        rt.configure(rt.parse_args(["--config", str(tmp_path / "missing.json")]), tmp_path)


# ---------------------------------------------------------------- main, snapshot, cli


def test_main_data_paths_relative_absolute_and_windows_style(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(rt, "snapshot", lambda cfg, data, today: seen.append(data) or 0)
    absolute = tmp_path / "abs"
    assert rt.main(["--data", "out/x"], base=tmp_path) == 0
    assert rt.main(["--data", str(absolute)], base=tmp_path) == 0
    assert rt.main(["--data", "~/rt-data"], base=tmp_path) == 0
    assert seen[0] == tmp_path / "out" / "x"
    assert seen[1] == absolute
    assert seen[2] == Path("~/rt-data").expanduser()
    if sys.platform == "win32":
        assert rt.main(["--data", "out\\y"], base=tmp_path) == 0
        assert seen[3] == tmp_path / "out" / "y"


def test_main_defaults_to_the_current_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen = []
    monkeypatch.setattr(rt, "snapshot", lambda cfg, data, today: seen.append(data) or 0)
    monkeypatch.setattr(sys, "argv", ["repo-traffic"])
    with pytest.raises(SystemExit) as e:
        rt.cli()
    assert e.value.code == 0 and seen == [tmp_path / "data"]


def test_main_logs_failed_in_the_data_folder_and_reraises(tmp_path, monkeypatch):
    def boom(cfg, data, today):
        raise RuntimeError("broken")

    monkeypatch.setattr(rt, "snapshot", boom)
    with pytest.raises(RuntimeError):
        rt.main(["--data", "d"], base=tmp_path)
    assert "FAILED RuntimeError('broken')" in (tmp_path / "d" / "run.log").read_text(encoding="utf-8")
    (tmp_path / "repo_traffic.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        rt.main([], base=tmp_path)
    assert "FAILED JSONDecodeError" in (tmp_path / "data" / "run.log").read_text(encoding="utf-8")


def stub_sources(monkeypatch, failures=(), notes=(), gsnap=None):
    monkeypatch.setattr(rt, "github_snapshot", lambda owner, f: f.extend(failures) or (gsnap or {}))
    monkeypatch.setattr(rt, "nuget_snapshot", lambda owner, f, n: n.extend(notes) or {})
    monkeypatch.setattr(rt, "npm_snapshot", lambda user, today, f: {})
    monkeypatch.setattr(rt, "pypi_snapshot", lambda names, today, f: {"p": {"daily": [], "last_month": 0}})


def test_snapshot_partial_gap_and_pypi(tmp_path, monkeypatch, capsys):
    stub_sources(monkeypatch, failures=["github repo list (gh exited 1)"], notes=["nuget replica down: x"])
    data = tmp_path / "data"
    data.mkdir()
    (data / "run.log").write_text("2026-09-01T09:00:00 ok 1 repos\n", encoding="utf-8")
    cfg = dict(rt.DEFAULTS, owner="o", nuget_owner="n", pypi_packages=["p"])
    assert rt.snapshot(cfg, data, TODAY) == 1
    out = capsys.readouterr()
    assert out.out.startswith("gap: 37 days")
    assert "repo-traffic: some sources failed, see run.log: github repo list (gh exited 1)" in out.err
    log = (data / "run.log").read_text(encoding="utf-8").splitlines()
    assert log[1].endswith(
        " gap: 37 days since the last run that saved GitHub traffic (2026-09-01); "
        "traffic from before 2026-09-24 was not saved"
    )
    assert log[2].endswith(
        " partial 0 repos, 0 npm, 0 nuget, 1 pypi; failed: github repo list (gh exited 1); nuget replica down: x"
    )
    summary = (data / "snapshots" / "2026-10-08" / "summary.md").read_text(encoding="utf-8")
    assert summary.startswith("# Repo traffic for o, 2026-10-08\n\n> gap: 37 days")
    assert "## Not counted this run\n\n- github repo list (gh exited 1)\n" in summary
    assert json.loads((data / "snapshots" / "2026-10-08" / "packages.json").read_text(encoding="utf-8"))["pypi"]


def test_snapshot_unknown_csv_header_is_a_failure(tmp_path, monkeypatch, capsys):
    stub_sources(monkeypatch)
    data = tmp_path / "data"
    data.mkdir()
    (data / "repos.csv").write_text("odd\n", encoding="utf-8")
    assert rt.snapshot(dict(rt.DEFAULTS, owner="o"), data, TODAY) == 1
    assert "repos.csv has an unknown header" in (data / "run.log").read_text(encoding="utf-8")
    assert (data / "repos.csv").read_text(encoding="utf-8") == "odd\n"
    assert (data / "downloads.csv").exists()


def test_snapshot_looks_up_the_owner(tmp_path, monkeypatch, capsys):
    stub_sources(monkeypatch)
    monkeypatch.setattr(rt, "gh_login", lambda: "me")
    assert rt.snapshot(dict(rt.DEFAULTS), tmp_path, TODAY) == 0
    assert (
        (tmp_path / "snapshots" / "2026-10-08" / "summary.md")
        .read_text(encoding="utf-8")
        .startswith("# Repo traffic for me, 2026-10-08")
    )


# ---------------------------------------------------------------- review findings (Phase 3, 2026-10-08)


def test_migration_keeps_rows_0_1_0_appended_in_the_new_width(tmp_path):
    # Finding 1: 0.1.0 appended 7-column rows under the 6-column header of the first test runs.
    path = tmp_path / "downloads.csv"
    path.write_bytes(
        b"snapshot,registry,package,last_14_days,last_month,total\r\n"
        b"2026-10-01,npm,p,9,30,\r\n"
        b"2026-10-02,nuget,Ex.Core,,,199,251\r\n"
        b"2026-10-02,github-release,alpha,,,,9\r\n"
    )
    f, w = rt.open_csv_for_append(path, rt.DOWNLOADS_HEADER, rt.DOWNLOADS_OLD_HEADERS)
    f.close()
    assert path.read_text(encoding="utf-8").splitlines()[1:] == [
        "2026-10-01,npm,p,9,30,,",
        "2026-10-02,nuget,Ex.Core,,,199,251",
        "2026-10-02,github-release,alpha,,,,9",
    ]


def test_migration_refuses_a_row_of_another_width(tmp_path):
    path = tmp_path / "downloads.csv"
    old = b"snapshot,registry,package,last_14_days,last_month,total\r\n1,2,3\r\n"
    path.write_bytes(old)
    with pytest.raises(ValueError, match="line 2 has 3 columns"):
        rt.open_csv_for_append(path, rt.DOWNLOADS_HEADER, rt.DOWNLOADS_OLD_HEADERS)
    assert path.read_bytes() == old and not (tmp_path / "downloads.csv.bak").exists()


def test_csv_with_a_byte_order_mark_is_read(tmp_path):
    # Finding 3: Excel's "CSV UTF-8" starts the file with U+FEFF.
    path = tmp_path / "repos.csv"
    path.write_bytes(b"\xef\xbb\xbf" + ",".join(rt.REPOS_HEADER).encode() + b"\r\n")
    f, w = rt.open_csv_for_append(path, rt.REPOS_HEADER)
    with f:
        w.writerow(["2026-10-08", "r", "false", "false", 1, 0, 0])
    assert path.read_bytes().endswith(b"\r\n2026-10-08,r,false,false,1,0,0\r\n")
    daily = tmp_path / "daily.csv"
    daily.write_bytes(b"\xef\xbb\xbfrepo,date,views,views_uniques,clones,clones_uniques\r\nr,2026-10-01,1,1,0,0\r\n")
    rt.merge_daily_csv(daily, {})
    assert daily.read_bytes() == b"repo,date,views,views_uniques,clones,clones_uniques\r\nr,2026-10-01,1,1,0,0\r\n"


def test_unknown_header_message_is_ascii(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("caf\u00e9,\u2603\n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        rt.open_csv_for_append(path, ["a"])
    assert str(e.value).isascii()


def test_say_replaces_what_the_console_cannot_show():
    class Console(io.TextIOWrapper):
        pass

    raw = io.BytesIO()
    stream = Console(raw, encoding="cp1252")
    rt.say("snow \u2603", stream)
    assert raw.getvalue() == b"snow ?\n"
    rt.say("plain", None)  # under pythonw sys.stdout can be None; print then does nothing


def test_http_json_retries_a_cut_off_body(monkeypatch, sleeps):
    # Finding 4: http.client.IncompleteRead is neither an OSError nor a ValueError.
    calls = []

    def urlopen(req, timeout=None):
        calls.append(1)
        if len(calls) == 1:
            raise rt.http.client.IncompleteRead(b"{")
        return FakeResponse(b"{}")

    monkeypatch.setattr(rt.urllib.request, "urlopen", urlopen)
    assert rt.http_json("https://a/") == {}
    assert sleeps == [5]
    assert issubclass(rt.http.client.IncompleteRead, rt.SOURCE_ERRORS)


def test_nuget_replica_in_an_unknown_shape_is_a_failure(web, sleeps):
    # Finding 10: a changed answer is not "a replica down" with exit 0.
    web[USNC] = [{"unexpected": True}]
    web[USSC] = [search(("A", 5))]
    failures, notes = [], []
    assert rt.nuget_snapshot("n", failures, notes) == {}
    assert failures == ["nuget search azuresearch-usnc (KeyError: 'data')"] and notes == []


def test_config_folder_is_the_settings_folder(tmp_path, monkeypatch):
    # Finding 5: `repo-traffic --config C:\rt\repo_traffic.json` from System32 writes next to the config.
    folder = tmp_path / "rt"
    folder.mkdir()
    (folder / "repo_traffic.json").write_text(json.dumps({"owner": "o"}), encoding="utf-8")
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    seen = []
    monkeypatch.setattr(rt, "snapshot", lambda cfg, data, today: seen.append((cfg["owner"], data)) or 0)
    assert rt.main(["--config", str(folder / "repo_traffic.json")]) == 0
    assert seen == [("o", folder / "data")]
    (folder / "repo_traffic.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError):
        rt.main(["--config", str(folder / "repo_traffic.json"), "--data", "out"])
    assert "FAILED JSONDecodeError" in (folder / "out" / "run.log").read_text(encoding="utf-8")


def test_no_abbreviated_flags():
    # Finding 6: --own must not mean --owner.
    with pytest.raises(SystemExit) as e:
        rt.parse_args(["--own", "a"])
    assert e.value.code == 2


def test_pypi_packages_as_a_string_in_the_config(tmp_path):
    # Finding 7.
    (tmp_path / "repo_traffic.json").write_text(json.dumps({"pypi_packages": "foo, bar"}), encoding="utf-8")
    assert rt.configure(rt.parse_args([]), tmp_path)["pypi_packages"] == ["foo", "bar"]
    (tmp_path / "repo_traffic.json").write_text(json.dumps({"pypi_packages": None}), encoding="utf-8")
    assert rt.configure(rt.parse_args([]), tmp_path)["pypi_packages"] == []


def test_retry_after_negative_or_not_a_number():
    # Finding 8.
    assert rt.retry_wait(http_error(429, {"Retry-After": "-5"}), 0) == 0.0
    assert rt.retry_wait(http_error(429, {"Retry-After": "nan"}), 0) == 10
    assert rt.retry_wait(http_error(429, {"Retry-After": "inf"}), 1) == 20
