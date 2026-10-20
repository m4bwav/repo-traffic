"""Unit tests for scripts/report.py, with gh faked in process. Names are invented."""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import report  # noqa: E402

HEADER = "repo,date,views,views_uniques,clones,clones_uniques\n"
DAILY = HEADER + (
    "alpha,2026-10-18,9,9,1,1\n"
    "alpha,2026-10-19,5,3,20,20\n"
    "beta,2026-10-19,12,7,25,25\n"
    "gamma,2026-10-19,0,0,0,0\n"
    "beta,2026-10-20,0,0,0,0\n"
)
TODAY = dt.date(2026, 10, 20)


def fake_pages(calls):
    def pages(path):
        calls.append(path)
        if path.startswith("repos/me/alpha/actions/runs?"):
            return [{"workflow_runs": [{"id": 1, "name": "ci"}, {"id": 2, "name": "npm in / - Update #7"}]}]
        if path.startswith("repos/me/alpha/actions/runs/1/jobs"):
            steps = [{"name": "Run actions/checkout@v5"}, {"name": "Post Run actions/checkout@v5"}]
            return [{"jobs": [{"steps": steps}, {"steps": steps}]}, {"jobs": [{"steps": None}]}]
        return [{"workflow_runs": []}] if "/runs?" in path else [{"jobs": []}]

    return pages


def setup(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "daily.csv").write_text(DAILY, encoding="utf-8")
    (tmp_path / "repo_traffic.json").write_text('{"owner": "me"}', encoding="utf-8")
    monkeypatch.setattr(report, "ROOT", tmp_path)


def test_pick_day_skips_today_and_empty_days():
    rows = [dict(zip(HEADER.strip().split(","), line.split(","))) for line in DAILY.strip().splitlines()[1:]]
    assert report.pick_day(rows, TODAY) == "2026-10-19"
    assert report.pick_day(rows, dt.date(2026, 10, 18)) is None


def test_checkout_steps_ignores_post_run():
    assert report.checkout_steps([{"jobs": [{"steps": [{"name": "Post Run actions/checkout@v5"}]}]}]) == 0


def test_report_subtracts_ci_and_caches(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    calls = []
    assert report.main(["--no-refresh"], today=TODAY, pages=fake_pages(calls)) == 0
    out = capsys.readouterr().out
    assert "Repo traffic for 2026-10-19" in out
    assert "| 1 | beta | 7 | 12 |" in out and "| 2 | alpha | 3 | 5 |" in out
    assert "| 1 | beta | 25 | 25 | 0 |" in out and "| 2 | alpha | 18 | 20 | 2 |" in out
    assert "gamma" not in out
    assert "(2 unique clones were CI checkouts)" in out
    cache = (tmp_path / "data" / "ci_checkouts.csv").read_text(encoding="utf-8")
    assert "alpha,2026-10-19,2,1" in cache
    n = len(calls)
    assert report.main(["--no-refresh"], today=TODAY, pages=fake_pages(calls)) == 0
    assert len(calls) == n  # the cached day costs no gh calls


def test_no_ci_and_explicit_day(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    assert report.main(["--no-refresh", "--no-ci", "--day", "2026-10-18"], today=TODAY, pages=None) == 0
    out = capsys.readouterr().out
    assert "| 1 | alpha | 9 | 9 |" in out and "CI" not in out


def test_today_is_not_cached(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    (tmp_path / "data" / "daily.csv").write_text(HEADER + "alpha,2026-10-20,1,1,3,3\n", encoding="utf-8")
    assert report.main(["--no-refresh", "--day", "2026-10-20"], today=TODAY, pages=fake_pages([])) == 0
    assert not (tmp_path / "data" / "ci_checkouts.csv").exists()


def test_no_traffic(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    (tmp_path / "data" / "daily.csv").write_text(HEADER, encoding="utf-8")
    assert report.main(["--no-refresh"], today=TODAY) == 1
    assert "no traffic" in capsys.readouterr().out


def test_refresh_runs_once_a_day(tmp_path, monkeypatch):
    runs = []

    class Done:
        returncode = 0

    monkeypatch.setattr(report.subprocess, "run", lambda *a, **k: runs.append(a) or Done())
    assert report.refresh(tmp_path, TODAY) is None and len(runs) == 1
    (tmp_path / "snapshots" / "2026-10-20").mkdir(parents=True)
    assert report.refresh(tmp_path, TODAY) is None and len(runs) == 1
