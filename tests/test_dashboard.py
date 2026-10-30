"""Unit tests for scripts/dashboard.py. Names are invented; nothing reaches the network."""

import datetime as dt
import http.client
import json
import os
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dashboard  # noqa: E402

DAILY = (
    "repo,date,views,views_uniques,clones,clones_uniques\n"
    "alpha,2026-10-20,4,2,10,5\n"
    "alpha,2026-10-23,6,3,2,1\n"
    "beta,2026-10-23,1,1,0,0\n"
)


def snap(data, day, at, stars, nuget_total, npm_daily):
    d = data / "snapshots" / day
    d.mkdir(parents=True, exist_ok=True)
    g = {
        "alpha": {
            "stars": stars,
            "forks": 0,
            "release_downloads": {"v1": {"a.zip": 3}},
            "views": {"count": 10, "uniques": 5, "views": []},
            "clones": {"count": 12, "uniques": 6, "clones": []},
        },
        "beta": {"stars": 1, "forks": 1, "release_downloads": {}, "views": None, "clones": None},
    }
    p = {
        "npm": {"pkg-a": {"daily": [{"day": k, "downloads": v} for k, v in npm_daily.items()], "last_month": 40}},
        "nuget": {"Lib.A": {"total": nuget_total, "last_6_weeks": 900, "versions": {}}},
        "pypi": {"py-a": {"daily": [], "last_month": 0}},
    }
    (d / "github.json").write_text(json.dumps(g), encoding="utf-8")
    (d / "packages.json").write_text(json.dumps(p), encoding="utf-8")
    t = dt.datetime.strptime(at, dashboard.STAMP).replace(tzinfo=dt.timezone.utc).timestamp()
    os.utime(d / "packages.json", (t, t))


@pytest.fixture
def data(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "daily.csv").write_text(DAILY, encoding="utf-8")
    snap(d, "2026-10-21", "2026-10-21T12:00:00Z", 2, 1000, {"2026-10-19": 1, "2026-10-20": 2})
    snap(d, "2026-10-24", "2026-10-24T12:00:00Z", 4, 1600, {"2026-10-20": 5, "2026-10-22": 3, "2026-10-23": 4})
    return d


NOW = dt.datetime(2026, 10, 24, 13, 0, tzinfo=dt.timezone.utc)


def test_record_backfills_once(data):
    assert dashboard.record(data) == ["2026-10-21T12:00:00Z", "2026-10-24T12:00:00Z"]
    assert dashboard.record(data) == []
    captures, series = dashboard.load_metrics(data)
    assert len(captures) == 2
    assert series[("nuget", "Lib.A", "total")] == [("2026-10-21T12:00:00Z", 1000), ("2026-10-24T12:00:00Z", 1600)]
    assert ("github", "beta", "views_14d") not in series  # no traffic access: no row
    assert series[("github", "alpha", "release_downloads")][0][1] == 3


def test_same_day_rerun_is_a_new_capture(data):
    dashboard.record(data)
    snap(data, "2026-10-24", "2026-10-24T18:00:00Z", 5, 1700, {"2026-10-23": 4})
    assert dashboard.record(data) == ["2026-10-24T18:00:00Z"]
    w = dashboard.compute(data, "last", NOW.replace(hour=19))
    nuget = next(p for p in w["packages"] if p["registry"] == "nuget")
    assert (nuget["downloads"], nuget["total"], w["span_hours"]) == (100, 1700, 6.0)


def test_window_48h(data):
    dashboard.record(data)
    w = dashboard.compute(data, "48h", NOW)
    assert w["start_day"] == "2026-10-22" and w["base"] == "2026-10-21T12:00:00Z"
    alpha = w["repos"][0]
    assert (alpha["name"], alpha["visitors"], alpha["views"], alpha["cloners"]) == ("alpha", 3, 6, 1)
    assert (alpha["stars"], alpha["stars_delta"]) == (4, 2)
    pk = {(p["registry"], p["name"]): p for p in w["packages"]}
    assert pk[("npm", "pkg-a")]["downloads"] == 7  # 3 + 4: days from 2026-10-22; the later snapshot wins 10-20
    assert pk[("nuget", "Lib.A")]["downloads"] == 600
    assert pk[("github-release", "alpha")]["downloads"] == 0
    assert pk[("pypi", "py-a")]["downloads"] == 0
    assert [p["name"] for p in w["packages"]][:2] == ["Lib.A", "pkg-a"]


def test_window_all_and_bad(data):
    dashboard.record(data)
    w = dashboard.compute(data, "all", NOW)
    assert w["repos"][0]["views"] == 10 and w["start_day"] == "the first day recorded"
    with pytest.raises(ValueError):
        dashboard.compute(data, "soon", NOW)


def test_summary_and_empty(tmp_path, data):
    assert "nothing recorded" in dashboard.summary_text(dashboard.compute(tmp_path, "48h", NOW))
    dashboard.record(data)
    out = dashboard.summary_text(dashboard.compute(data, "48h", NOW))
    assert "| 1 | alpha | 3 | 6 | 1 | 2 | 4 | +2 |" in out
    assert "| 1 | nuget | Lib.A | 600 | captures |" in out
    assert "py-a" not in out


def test_html_is_self_contained(data):
    dashboard.record(data)
    page = dashboard.render_html(data, now=NOW)
    assert "__DATA__" not in page and "src=" not in page and "<link" not in page
    blob = page.split("const D=")[1].split(",LIVE=")[0]
    payload = json.loads(blob)
    assert set(payload["windows"]) == set(dashboard.WINDOWS)
    assert payload["series"]["packages"]["nuget/Lib.A"]["points"] == [["2026-10-24T12:00:00Z", 200.0]]


def test_build_and_summary_cli(data, monkeypatch, capsys):
    monkeypatch.setattr(dashboard, "data_folder", lambda: data)
    assert dashboard.main(["build"]) == 0
    assert (data / "dashboard.html").exists()
    assert dashboard.main(["capture", "--no-snapshot", "--window", "all"]) == 0
    assert "Window all" in capsys.readouterr().out


def test_capture_runs_snapshot(data, monkeypatch, capsys):
    monkeypatch.setattr(dashboard, "data_folder", lambda: data)

    class Done:
        returncode = 1

    monkeypatch.setattr(dashboard.subprocess, "run", lambda *a, **k: Done())
    assert dashboard.main(["capture", "--window", "7d"]) == 0
    assert "snapshot exited 1" in capsys.readouterr().out
    with pytest.raises(ValueError):
        dashboard.main(["capture", "--window", "x"])


def test_server_checks_host_and_header(data, monkeypatch):
    monkeypatch.setattr(dashboard, "capture", lambda d: (None, ["t"]))
    server = dashboard.make_server(data, 0)
    port = server.server_address[1]
    server.server_close()
    server = dashboard.make_server(data, port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:

        def req(method, path, headers=None):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request(method, path, headers=headers or {})
            r = c.getresponse()
            return r.status, r.read().decode()

        status, body = req("GET", "/")
        assert status == 200 and "repo-traffic" in body and "LIVE=true" in body
        assert req("GET", "/", {"Host": "evil.example:%d" % port})[0] == 403
        assert req("POST", "/capture")[0] == 403
        assert req("POST", "/capture", {"X-Capture": "1"})[0] == 202
        assert req("GET", "/nope")[0] == 404
    finally:
        server.shutdown()
        server.server_close()


def test_window_start_bounds_in_payload(data):
    dashboard.record(data)
    payload = json.loads(dashboard.render_html(data, now=NOW).split("const D=")[1].split(",LIVE=")[0])
    starts = {w: payload["windows"][w]["start"] for w in dashboard.WINDOWS}
    assert starts["all"] is None
    assert starts["last"] == "2026-10-21T12:00:00Z"
    assert starts["24h"] == "2026-10-23T13:00:00Z"
    assert starts["7d"] == "2026-10-17T13:00:00Z"
    series = payload["series"]
    assert series["packages"]["nuget/Lib.A"]["basis"] == "captures"
    assert series["packages"]["npm/pkg-a"]["basis"] == "daily"
    assert series["any"] is True


def test_link_urls_per_registry():
    link = dashboard.link_for
    assert link("repos", {"name": "alpha"}, "someone") == "https://github.com/someone/alpha"
    assert link("repos", {"name": "alpha"}, None) is None
    assert link("packages", {"registry": "npm", "name": "@s/p"}, "o") == "https://www.npmjs.com/package/@s/p"
    assert link("packages", {"registry": "nuget", "name": "Lib.A"}, "o") == "https://www.nuget.org/packages/Lib.A"
    assert link("packages", {"registry": "pypi", "name": "py-a"}, "o") == "https://pypi.org/project/py-a/"
    assert link("packages", {"registry": "openupm", "name": "com.x.y"}, "o") == "https://openupm.com/packages/com.x.y/"
    rel = {"registry": "github-release", "name": "alpha"}
    assert link("packages", rel, "o") == "https://github.com/o/alpha/releases"


def test_owner_links_in_page_and_escaping(data):
    (data / "daily.csv").write_text(DAILY + "<b>x</b>,2026-10-23,1,1,0,0" + chr(10), encoding="utf-8")
    dashboard.record(data)
    page = dashboard.render_html(data, now=NOW, owner="someone")
    payload = json.loads(page.split("const D=")[1].split(",LIVE=")[0])
    rows = {r["name"]: r for r in payload["windows"]["all"]["repos"]}
    assert rows["alpha"]["url"] == "https://github.com/someone/alpha"
    assert "<b>x</b>" not in page  # names reach the page only as JSON; the script escapes them in cells
    assert 'target="_blank" rel="noopener"' in page and "esc(r.url)" in page and "esc(r[c])" in page
