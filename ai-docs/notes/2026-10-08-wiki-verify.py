"""Runs every example on the repo-traffic wiki against the installed package and prints what each one printed.

Usage:
  python wiki-verify.py                       install repo-traffic VERSION into a fresh venv and run every case
  python wiki-verify.py --check-pages WIKI    check that every command and file block on the pages is in this program

Every case runs the installed package. The cases that need GitHub, npm, NuGet or pypistats go through the
repository's golden harness (tests/golden/harness.py): a fake gh first on PATH, a local HTTP server for the
registries, a fixed clock, recorded sleeps and a socket guard that refuses every address but 127.0.0.1. The cases
that need no network (--help, --version, bad arguments) run the real repo-traffic command with no gh on PATH and
the proxy pointed at a closed local port. Every owner, repository and package name is invented.

Three ways of starting the tool are driven through the harness:
  file     python repo_traffic.py: the installed repo_traffic.py itself, copied into the case folder (a clone)
  command  repo-traffic: a driver that imports the installed module and calls repo_traffic.cli(), which is what the
           console script does; the harness has to patch the clock and the network inside the process
  module   python -m repo_traffic: a driver that runs the installed module with runpy, as -m does

Environment:
  WIKI_VERIFY_REPO     the repository clone, for tests/golden/ and install-task.ps1 (default: two folders up)
  WIKI_VERIFY_SOURCE   what pip installs (default repo-traffic==VERSION; a wheel path works)
  WIKI_VERIFY_PYTHON   an interpreter that already has the package (skips creating the venv; used on Linux)
  WIKI_VERIFY_SCRATCH  scratch folder (default: <temp>/repo-traffic-wiki-verify)
  WIKI_VERIFY_TASKS=1  Windows: register the scheduled tasks under a test name, print them, and remove them
  WIKI_VERIFY_PIPX=1   install and uninstall with pipx in the scratch folder

Output goes to stdout and to --out (default wiki-verify.out.txt beside this file), with LF line endings.
"""

import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VERSION = "1.0.0b1"
HERE = Path(__file__).resolve().parent
WINDOWS = sys.platform == "win32"
TEST_TASK = "repo-traffic-wiki-verify"

# ---------------------------------------------------------------- the examples the pages show
# Every command and file a page shows is here as text, and the cases below run it. --check-pages compares.

EXAMPLES = {
    # Getting-Started
    "pipx": "pipx install repo-traffic",
    "pipx-uninstall": "pipx uninstall repo-traffic",
    "version": "repo-traffic --version",
    "module-version": "python -m repo_traffic --version",
    "first-run": "repo-traffic",
    "config-run": "repo-traffic",
    "clone-run": "python repo_traffic.py",
    # Commands-And-Options
    "help": "repo-traffic --help",
    "flag-over-config": "repo-traffic --top 2 --nuget-owner nuget-example",
    "pypi-flag": "repo-traffic --owner octo-example --pypi-packages octo-tool,Octo_Helper",
    "config-folder": "repo-traffic --config settings/repo_traffic.json",
    "module-no-config": "python -m repo_traffic",
    "module-config": "python -m repo_traffic --config repo_traffic.json",
    "top-no-value": "repo-traffic --top",
    "abbreviation": "repo-traffic --own octo-example",
    "unknown-flag": "repo-traffic --owners octo-example",
    "top-not-a-number": "repo-traffic --top many",
    "bad-json": "repo-traffic",
    "missing-config": "repo-traffic --config settings/missing.json",
    "partial": "repo-traffic",
}

# The configuration files the pages show.
CONFIG_EXAMPLE = """{
  "owner": "octo-example",
  "npm_user": "npm-example",
  "nuget_owner": "nuget-example",
  "pypi_packages": ["octo-tool"],
  "data": "data",
  "top": 10
}
"""
CONFIG_FLAGS = """{
  "owner": "octo-example",
  "npm_user": "npm-example",
  "nuget_owner": null,
  "top": 10
}
"""
CONFIG_SETTINGS = """{
  "owner": "octo-example",
  "data": "traffic"
}
"""
CONFIG_TYPO = """{
  "owner": "octo-example",
  "npm-user": "npm-example"
}
"""
CONFIG_BAD = """{
  "owner": "octo-example",
}
"""

# Scheduling: the files and commands the Scheduling page shows.
INSTALL_TASK = "pwsh -File install-task.ps1"
INSTALL_TASK_ARGS = "pwsh -File install-task.ps1 -Days 13 -At 09:00 -Name repo-traffic"
PIPX_TASK = r"""
$exe = (Get-Command repo-traffic).Source
$folder = "$HOME\repo-traffic-data"
$action = New-ScheduledTaskAction -Execute $exe -WorkingDirectory $folder `
    -Argument "--config `"$folder\repo_traffic.json`""
$trigger = New-ScheduledTaskTrigger -Daily -DaysInterval 13 -At 09:00
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName repo-traffic -Action $action -Trigger $trigger -Settings $settings
"""
# Not run: they act on the task named repo-traffic, and tasks() registers only TEST_TASK.
TASK_MANAGE = """Get-ScheduledTask -TaskName repo-traffic | Get-ScheduledTaskInfo
Start-ScheduledTask -TaskName repo-traffic
Unregister-ScheduledTask -TaskName repo-traffic -Confirm:$false"""
CRON_LINE = '0 9 * * 1 cd "$HOME/repo-traffic-data" && "$HOME/.local/bin/repo-traffic"'
CRON_README = '0 9 1,15 * * cd /path/to/your/data-folder && "$HOME/.local/bin/repo-traffic"'
SYSTEMD_SERVICE = """[Unit]
Description=Save GitHub traffic and package downloads (repo-traffic)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=%h/repo-traffic-data
ExecStart=%h/.local/bin/repo-traffic
"""
SYSTEMD_TIMER = """[Unit]
Description=Run repo-traffic every Monday

[Timer]
OnCalendar=Mon *-*-* 09:00:00
Persistent=true

[Install]
WantedBy=timers.target
"""
SYSTEMD_ENABLE = """mkdir -p ~/.config/systemd/user ~/repo-traffic-data
cp repo-traffic.service repo-traffic.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now repo-traffic.timer
loginctl enable-linger "$USER"
systemctl --user list-timers repo-traffic.timer"""
LAUNCHD_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.example.repo-traffic</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/you/.local/bin/repo-traffic</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/you/repo-traffic-data</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>1</integer>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/Users/you/repo-traffic-data/launchd.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/you/repo-traffic-data/launchd.log</string>
</dict>
</plist>
"""
LAUNCHD_LOAD = """launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.repo-traffic.plist
launchctl kickstart gui/$(id -u)/com.example.repo-traffic"""
LAUNCHD_UNLOAD = "launchctl bootout gui/$(id -u)/com.example.repo-traffic"
# Development: the repository's own commands, from AGENTS.md (run once by hand for the note, not by this program).
DEVELOPMENT = """git clone https://github.com/m4bwav/repo-traffic.git
python -m pip install -r requirements-dev.txt
python -m pytest
python -m coverage run -m pytest && python -m coverage report
python -m ruff check . && python -m ruff format --check .
python -m build && python -m twine check --strict dist/* && python scripts/check_size.py
python tests/golden/capture.py --check
REPO_TRAFFIC_WRITE_EXCEPTIONS=1 python -m pytest tests/test_golden.py
REPO_TRAFFIC_SCRIPT=/path/to/site-packages/repo_traffic.py python -m pytest tests/test_golden.py
git tag v1.0.0 && git push origin v1.0.0"""

# Shown on the pages and not run here, with the reason (the pages say "not tested" or why).
NOT_RUN = {
    "python -m pip install --user repo-traffic": "installs into the user's own site-packages; setup() runs the "
    "same pip install into a fresh venv",
    "gh auth login": "signs in to the real GitHub",
    "gh auth status": "asks the real GitHub",
    "pipx ensurepath": "changes the user's PATH",
    "command -v repo-traffic": "prints a machine path",
    "crontab -e": "edits the real crontab",
    "where repo-traffic": "prints a machine path",
}

# ---------------------------------------------------------------- output

LINES = []


def out(text=""):
    LINES.append(text)
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))


def section(title):
    out("")
    out("=== %s ===" % title)


MASKS = []


def mask(text):
    for real, shown in MASKS:
        if real:
            text = text.replace(real, shown)
    return text


def endings(text):
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    if crlf and not lf:
        return "CRLF"
    if lf and not crlf:
        return "LF"
    if not crlf and not lf:
        return "no line ending"
    return "mixed (%d CRLF, %d LF)" % (crlf, lf)


def tree(paths):
    """The data folder as the README draws it."""
    lines, seen = [], set()
    for p in sorted(paths):
        parts = p.split("/")
        for depth in range(len(parts) - 1):
            folder = "/".join(parts[: depth + 1])
            if folder not in seen:
                seen.add(folder)
                lines.append("  " * depth + parts[depth] + "/")
        lines.append("  " * (len(parts) - 1) + parts[-1])
    return lines


# ---------------------------------------------------------------- setup


def setup():
    repo = Path(os.environ.get("WIKI_VERIFY_REPO") or HERE.parents[1]).resolve()
    if not (repo / "tests" / "golden" / "harness.py").exists():
        sys.exit("WIKI_VERIFY_REPO must be the repo-traffic clone (tests/golden/harness.py not found under %s)" % repo)
    scratch = Path(os.environ.get("WIKI_VERIFY_SCRATCH") or Path(tempfile.gettempdir()) / "repo-traffic-wiki-verify")
    scratch.mkdir(parents=True, exist_ok=True)
    python = os.environ.get("WIKI_VERIFY_PYTHON")
    source = os.environ.get("WIKI_VERIFY_SOURCE") or "repo-traffic==" + VERSION
    if python:
        source = "an interpreter given in WIKI_VERIFY_PYTHON, with %s installed beforehand" % source
    else:
        venv = scratch / "venv"
        if venv.exists():
            shutil.rmtree(venv)
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        python = str(venv / ("Scripts/python.exe" if WINDOWS else "bin/python"))
        subprocess.run(
            [python, "-m", "pip", "install", "-q", "--no-cache-dir", "--disable-pip-version-check", source], check=True
        )
    info = json.loads(
        subprocess.run(
            [
                python,
                "-c",
                "import json, sys, sysconfig, importlib.metadata as m, repo_traffic as r; print(json.dumps("
                "{'file': r.__file__, 'version': r.__version__, 'dist': m.version('repo-traffic'), "
                "'requires': m.requires('repo-traffic'), 'python': sys.version.split()[0], "
                "'purelib': sysconfig.get_paths()['purelib'], 'scripts': sysconfig.get_paths()['scripts']}))",
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(scratch),
        ).stdout
    )
    MASKS.extend(
        [
            (info["purelib"], "<site-packages>"),
            (info["scripts"], "<scripts>"),
            (str(scratch), "<scratch>"),
            (str(repo), "<repo>"),
        ]
    )
    sys.path.insert(0, str(repo / "tests" / "golden"))
    return repo, scratch, python, source, info


# ---------------------------------------------------------------- the three ways to start it

COMMAND_DRIVER = """import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.curdir) != here]
import repo_traffic

repo_traffic.cli()
"""
MODULE_DRIVER = """import os
import runpy
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.curdir) != here]
runpy.run_module("repo_traffic", run_name="__main__", alter_sys=True)
"""


def drivers(scratch, info):
    d = scratch / "drivers"
    d.mkdir(exist_ok=True)
    (d / "command").mkdir(exist_ok=True)
    (d / "module").mkdir(exist_ok=True)
    (d / "command" / "repo_traffic.py").write_text(COMMAND_DRIVER, encoding="utf-8")
    (d / "module" / "repo_traffic.py").write_text(MODULE_DRIVER, encoding="utf-8")
    return {
        "file": Path(info["file"]),
        "command": d / "command" / "repo_traffic.py",
        "module": d / "module" / "repo_traffic.py",
    }


# ---------------------------------------------------------------- fixtures (invented names, shaped like cases.py)


def fixtures():
    import cases as c

    def pypi(packages, today_window=("2026-09-24", "2026-10-07")):
        """packages: name -> (daily counts over the 14-day window, last_month). Adds rows the tool must drop:
        a day before the window, today, and the with_mirrors series."""
        import datetime

        http = {}
        first = datetime.date.fromisoformat(today_window[0])
        for name, (daily, month) in packages.items():
            slug = re.sub(r"[-_.]+", "-", name).lower()
            rows = [
                {
                    "category": "without_mirrors",
                    "date": (first - datetime.timedelta(days=1)).isoformat(),
                    "downloads": 99,
                }
            ]
            for i, n in enumerate(daily):
                day = (first + datetime.timedelta(days=i)).isoformat()
                rows.append({"category": "with_mirrors", "date": day, "downloads": n + 5})
                rows.append({"category": "without_mirrors", "date": day, "downloads": n})
            rows.append({"category": "without_mirrors", "date": "2026-10-08", "downloads": 7})
            base = "pypistats.org/api/packages/%s/" % slug
            http[base + "recent"] = [
                {
                    "status": 200,
                    "json": {
                        "data": {"last_day": daily[-1], "last_week": sum(daily[-7:]), "last_month": month},
                        "package": slug,
                        "type": "recent_downloads",
                    },
                }
            ]
            http[base + "overall?mirrors=false"] = [
                {"status": 200, "json": {"data": rows, "package": slug, "type": "overall_downloads"}}
            ]
        return http

    return c, pypi


# Files whose text each case prints (every file's name, line endings and size are printed for every case).
SHOW = (".csv", ".bak", "run.log", "summary.md")


def make_cases():
    c, pypi = fixtures()
    full_http = {**c.NPM_1, **c.NUGET_1, **pypi({"octo-tool": ([0, 3, 1, 0, 2, 5, 1, 0, 0, 4, 2, 1, 0, 3], 30)})}
    config_example = json.loads(CONFIG_EXAMPLE)
    gh_only = c.github(traffic=c.TRAFFIC_1, releases=c.RELEASES)

    def run(**kw):
        return c.run(**kw)

    cases = {}

    def add(name, form, config=None, files=None, runs=None, shown=None, show=SHOW):
        cases[name] = {
            "form": form,
            "shown": shown,
            "show": show,
            "case": {"config": config, "files": files or {}, "runs": runs},
        }

    # Home and Getting-Started
    add("first-run", "command", runs=[run(http={})], shown=EXAMPLES["first-run"])
    add("config-run", "command", config=config_example, runs=[run(http=full_http)], shown=EXAMPLES["config-run"])
    add("clone-run", "file", config=config_example, runs=[run(http=full_http)], shown=EXAMPLES["clone-run"])
    # Commands-And-Options
    add(
        "flag-over-config",
        "command",
        config=json.loads(CONFIG_FLAGS),
        runs=[run(args=EXAMPLES["flag-over-config"].split()[1:], http=full_http)],
        shown=EXAMPLES["flag-over-config"],
    )
    add(
        "pypi-flag",
        "command",
        runs=[
            run(
                args=EXAMPLES["pypi-flag"].split()[1:],
                http=pypi(
                    {"octo-tool": ([0, 3, 1, 0, 2, 5, 1, 0, 0, 4, 2, 1, 0, 3], 30), "Octo_Helper": ([1] * 14, 15)}
                ),
            )
        ],
        shown=EXAMPLES["pypi-flag"],
    )
    add(
        "config-folder",
        "command",
        files={"settings/repo_traffic.json": CONFIG_SETTINGS},
        runs=[run(args=EXAMPLES["config-folder"].split()[1:], http={})],
        shown=EXAMPLES["config-folder"],
    )
    add("module-no-config", "module", config=c.CONFIG, runs=[run(http={})], shown=EXAMPLES["module-no-config"])
    add(
        "module-config",
        "module",
        config={"owner": c.OWNER},
        runs=[run(args=EXAMPLES["module-config"].split()[3:], http={})],
        shown=EXAMPLES["module-config"],
    )
    add("bad-json", "command", files={"repo_traffic.json": CONFIG_BAD}, runs=[run(http={})], shown=EXAMPLES["bad-json"])
    add(
        "missing-config",
        "command",
        runs=[run(args=EXAMPLES["missing-config"].split()[1:], http={})],
        shown=EXAMPLES["missing-config"],
    )
    add(
        "partial",
        "command",
        config=c.CONFIG,
        runs=[
            run(
                http=c.with_http(
                    {
                        "api.npmjs.org/downloads/range/2026-09-24:2026-10-07/alpha-lib": [
                            {"status": 429, "body": "Too Many Requests"}
                        ]
                    }
                )
            )
        ],
        shown=EXAMPLES["partial"],
    )
    # Output-Files
    add("full", "command", config=config_example, runs=[run(http=full_http)], shown="repo-traffic", show=True)
    second_http = {**c.NPM_2, **c.NUGET_1, **pypi({"octo-tool": ([1] * 14, 31)}, ("2026-10-07", "2026-10-20"))}
    add(
        "second-run",
        "command",
        config=config_example,
        runs=[
            run(http=full_http),
            run(now=c.NOW_2, gh=c.github(traffic=c.TRAFFIC_2, releases=c.RELEASES), http=second_http),
        ],
        shown="repo-traffic",
    )
    add("same-day-twice", "command", config={"owner": c.OWNER}, runs=[run(http={}), run(http={})], shown="repo-traffic")
    add(
        "old-header",
        "command",
        config=c.CONFIG,
        files={"data/downloads.csv": c.OLD_HEADER},
        runs=[run()],
        shown="repo-traffic",
    )
    add(
        "unknown-header",
        "command",
        config={"owner": c.OWNER},
        files={"data/downloads.csv": "date,package,count\r\n2026-10-01,alpha-lib,9\r\n"},
        runs=[run(http={})],
        shown="repo-traffic",
    )
    add(
        "odd-width-row",
        "command",
        config=c.CONFIG,
        files={"data/downloads.csv": c.OLD_HEADER + "2026-10-02,npm,alpha-lib\r\n"},
        runs=[run()],
        shown="repo-traffic",
    )
    add(
        "bom-daily",
        "command",
        config={"owner": c.OWNER},
        files={
            "data/daily.csv": "\ufeffrepo,date,views,views_uniques,clones,clones_uniques\r\n"
            "alpha-lib,2026-09-20,4,2,0,0\r\n"
        },
        runs=[run(http={})],
        shown="repo-traffic",
    )
    # Data-Sources-And-Limits
    add(
        "no-push-access",
        "command",
        config={"owner": c.OWNER},
        runs=[run(gh=c.github(traffic=c.TRAFFIC_1, releases=c.RELEASES, no_access=("gamma-private",)), http={})],
        shown="repo-traffic",
        show=SHOW + ("github.json",),
    )
    add("unknown-key", "command", files={"repo_traffic.json": CONFIG_TYPO}, runs=[run(http={})], shown="repo-traffic")
    add(
        "npm-429-then-ok",
        "command",
        config={"owner": c.OWNER, "npm_user": c.NPM_USER},
        runs=[
            run(
                http=c.with_http(
                    {
                        "api.npmjs.org/downloads/range/2026-09-24:2026-10-07/alpha-lib": [
                            {"status": 429, "body": "Too Many Requests"},
                            {"status": 429, "body": "Too Many Requests"},
                        ]
                        + c.NPM_1["api.npmjs.org/downloads/range/2026-09-24:2026-10-07/alpha-lib"]
                    }
                )
            )
        ],
        shown="repo-traffic",
    )
    add(
        "npm-empty-body",
        "command",
        config={"owner": c.OWNER, "npm_user": c.NPM_USER},
        runs=[
            run(
                http=c.with_http(
                    {"api.npmjs.org/downloads/point/last-month/@octo-example/beta": [{"status": 200, "body": ""}]}
                )
            )
        ],
        shown="repo-traffic",
    )
    add(
        "nuget-replica-down",
        "command",
        config={"owner": c.OWNER, "nuget_owner": c.NUGET_OWNER},
        runs=[run(down=[c.USSC])],
        shown="repo-traffic",
    )
    add(
        "nuget-replica-503",
        "command",
        config={"owner": c.OWNER, "nuget_owner": c.NUGET_OWNER},
        runs=[run(http=c.with_http({c.USNC + c.NUGET_QUERY: [{"status": 503, "body": "Service Unavailable"}]}))],
        shown="repo-traffic",
    )
    add(
        "nuget-both-down",
        "command",
        config={"owner": c.OWNER, "nuget_owner": c.NUGET_OWNER},
        runs=[run(down=[c.USNC, c.USSC])],
        shown="repo-traffic",
    )
    add(
        "nuget-stats-404",
        "command",
        config={"owner": c.OWNER, "nuget_owner": c.NUGET_OWNER},
        runs=[
            run(
                http=c.nuget(
                    usnc={"Example.Core": (0, {"1.0.0": 0})},
                    ussc={"Example.Core": (7, {"1.0.0": 7})},
                    reports={"Example.Core": None},
                )
            )
        ],
        shown="repo-traffic",
    )
    add(
        "pypi-404",
        "command",
        config={"owner": c.OWNER, "pypi_packages": ["octo-tool", "not-on-pypi"]},
        runs=[run(http=pypi({"octo-tool": ([1] * 14, 15)}))],
        shown="repo-traffic",
    )
    add(
        "gap",
        "command",
        config={"owner": c.OWNER},
        files={"data/run.log": "2026-10-15T09:00:00 ok 4 repos, 0 npm, 0 nuget\n"},
        runs=[run(now="2026-11-01T09:00:00", http={})],
        shown="repo-traffic",
    )
    add(
        "gap-partial-counts",
        "command",
        config={"owner": c.OWNER},
        files={
            "data/run.log": "2026-10-15T09:00:00 ok 4 repos, 0 npm, 0 nuget\n"
            "2026-10-22T09:00:00 partial 4 repos, 0 npm, 0 nuget; failed: npm search (HTTP 503)\n"
            "2026-10-29T09:00:00 partial 0 repos, 0 npm, 0 nuget; failed: github repo list (gh exited 1)\n"
        },
        runs=[run(now="2026-11-01T09:00:00", http={})],
        shown="repo-traffic",
    )
    add(
        "gh-not-logged-in",
        "command",
        runs=[
            run(
                gh={
                    "api user -q .login": {
                        "code": 1,
                        "stderr": "To get started with GitHub CLI, please run:  gh auth login\n",
                    }
                },
                http={},
            )
        ],
        shown="repo-traffic",
    )
    add(
        "repo-list-fails",
        "command",
        config={"owner": c.OWNER},
        runs=[run(gh={"api user -q .login": {"stdout": c.OWNER + "\n"}}, http={})],
        shown="repo-traffic",
    )
    add("top-zero", "command", config={"owner": c.OWNER, "top": 0}, runs=[run(http={})], shown="repo-traffic")
    del gh_only
    return cases


# ---------------------------------------------------------------- running and printing


def print_files(files, show):
    out("files written:")
    for path in sorted(files):
        text = files[path]
        bom = ", starts with a byte order mark" if text.startswith("﻿") else ""
        out("  %s  (%s, %d bytes as text%s)" % (path, endings(text), len(text), bom))
    for path in sorted(files):
        if show is True or any(path.endswith(s) for s in show):
            out("--- %s" % path)
            body = files[path].replace("\r\n", "\n")
            out(body[:-1] if body.endswith("\n") else body)


def run_harness_case(harness, scripts, python, name, spec, show=True):
    section("case: %s" % name)
    form = spec["form"]
    out(
        "form: %s"
        % {
            "file": "python repo_traffic.py (the installed module copied into the folder)",
            "command": "repo-traffic (repo_traffic.cli() of the installed module)",
            "module": "python -m repo_traffic (runpy on the installed module)",
        }[form]
    )
    case = spec["case"]
    if case["config"] is not None:
        out("repo_traffic.json: %s" % json.dumps(case["config"]))
    for path, text in sorted(case["files"].items()):
        out("before: %s (%s)" % (path, endings(text)))
        body = text.replace("\r\n", "\n").lstrip("\ufeff")
        out(body[:-1] if body.endswith("\n") else body)
    records = harness.run_case(str(scripts[form]), case, python=python)
    for n, (r, rec) in enumerate(zip(case["runs"], records)):
        out("--- run %d at %s" % (n + 1, r["now"]))
        command = (
            spec["shown"]
            if not r["args"] or spec["shown"].endswith(" ".join(r["args"]))
            else (spec["shown"] + " " + " ".join(r["args"]))
        )
        out("$ " + command)
        stdout = mask(rec["stdout"]).replace("\r\n", "\n")
        if stdout.endswith("\n"):
            stdout = stdout[:-1]
        if stdout:
            out(stdout)
        if rec["stderr_last"]:
            out(mask(rec["stderr_last"]))
        out("$ echo $?")
        out(str(rec["exit"]))
        out("stdout ends: %s" % ("nothing printed" if not rec["stdout"] else endings(rec["stdout"])))
        out("stderr last line: %s" % (mask(rec["stderr_last"]) or "(empty)"))
        out(
            "gh calls: %d; first: %s" % (len(rec["gh_calls"]), " ".join(rec["gh_calls"][0]) if rec["gh_calls"] else "-")
        )
        out("http requests: %d" % len(rec["requests"]))
        for q in rec["requests"]:
            out("  GET https://%s  (User-Agent: %s)" % (q["url"], q["user_agent"]))
        out("sleeps: %s" % (", ".join("%g" % s for s in rec["sleeps"]) or "none"))
        files = {k: mask(v) for k, v in rec["files"].items()}
        out("the folder afterwards:")
        for line in tree([k for k in files]):
            out(line)
        print_files(files, show)
    return records


def real(cmd, python, scripts_dir, cwd):
    """Run the real installed command with no gh on PATH and no way out to the network."""
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("PATH", "PYTHONPATH", "GH_TOKEN", "GITHUB_TOKEN")}
    system = [os.environ.get("SYSTEMROOT", r"C:\Windows") + r"\System32"] if WINDOWS else ["/usr/bin", "/bin"]
    env["PATH"] = os.pathsep.join([scripts_dir] + system)
    env.update({"HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "PYTHONIOENCODING": "utf-8"})
    argv = cmd.split()
    if argv[0] == "python":
        argv[0] = python
    else:
        argv[0] = str(Path(scripts_dir) / (argv[0] + (".exe" if WINDOWS else "")))
    return subprocess.run(argv, cwd=str(cwd), env=env, capture_output=True)


def real_case(label, cmd, python, info, scratch):
    section("command: %s" % label)
    cwd = scratch / ("real-" + label)
    if cwd.exists():
        shutil.rmtree(cwd)
    cwd.mkdir()
    p = real(cmd, python, info["scripts"], cwd)
    so = mask(p.stdout.decode("utf-8")).replace("\r\n", "\n").rstrip("\n")
    se = mask(p.stderr.decode("utf-8")).replace("\r\n", "\n").rstrip("\n")
    out("$ " + cmd)
    if so:
        out(so)
    if se:
        out(se)
    out("$ echo $?")
    out(str(p.returncode))
    out("stdout: %s" % ("%d lines" % len(so.split("\n")) if so else "(empty)"))
    out("stderr: %s" % ("%d lines" % len(se.split("\n")) if se else "(empty)"))
    left = sorted(x.relative_to(cwd).as_posix() for x in cwd.rglob("*"))
    out("files left in the folder: %s" % (", ".join(left) or "none"))


def ps(script):
    return subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True)


TASK_READBACK = """$t = Get-ScheduledTask -TaskName '%s'
$a = $t.Actions[0]
'Execute: ' + $a.Execute
'Arguments: ' + $a.Arguments
'WorkingDirectory: ' + $a.WorkingDirectory
$tr = $t.Triggers[0]
$at = $tr.StartBoundary.Substring(11, 8)
'Trigger: ' + $tr.CimClass.CimClassName + ', DaysInterval ' + $tr.DaysInterval + ', at ' + $at
$s = $t.Settings
'StartWhenAvailable: ' + $s.StartWhenAvailable
'DisallowStartIfOnBatteries: ' + $s.DisallowStartIfOnBatteries
'StopIfGoingOnBatteries: ' + $s.StopIfGoingOnBatteries
'ExecutionTimeLimit: ' + $s.ExecutionTimeLimit
'LogonType: ' + $t.Principal.LogonType
"""


def tasks(repo, scratch, info):
    section("scheduling: Windows tasks (registered as %s, read back, removed)" % TEST_TASK)
    existing = ps("Get-ScheduledTask -TaskName '%s' -ErrorAction SilentlyContinue" % TEST_TASK)
    if existing.stdout.strip():
        out("a task named %s exists already; skipped" % TEST_TASK)
        return
    folder = scratch / "task"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir()
    shutil.copyfile(repo / "install-task.ps1", folder / "install-task.ps1")
    shutil.copyfile(info["file"], folder / "repo_traffic.py")
    python = shutil.which("python")
    MASKS.extend([(str(Path(python).parent), "<python folder>"), (str(Path.home()), "<home>")])
    out("$ " + INSTALL_TASK_ARGS)
    p = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(folder / "install-task.ps1"),
            "-Days",
            "13",
            "-At",
            "09:00",
            "-Name",
            TEST_TASK,
        ],
        capture_output=True,
        text=True,
    )
    # The table install-task.ps1 prints, without colour codes and with the date the next run falls on masked.
    table = re.sub(r"\x1b\[[0-9;]*m", "", p.stdout).strip().replace(TEST_TASK, "repo-traffic")
    out(re.sub(r"\d{1,2}/\d{1,2}/\d{4} 9:00:00 AM", "<13 days from the first 09:00> 9:00:00 AM", table))
    if p.returncode:
        out("exit %d: %s" % (p.returncode, mask(p.stderr.strip())))
        return
    out("read back:")
    out(mask(ps(TASK_READBACK % TEST_TASK).stdout.rstrip()).replace("<scratch>\\task", "<clone>"))
    ps("Unregister-ScheduledTask -TaskName '%s' -Confirm:$false" % TEST_TASK)
    out(
        "removed: %s"
        % (
            "yes"
            if not ps("Get-ScheduledTask -TaskName '%s' -ErrorAction SilentlyContinue" % TEST_TASK).stdout.strip()
            else "NO"
        )
    )
    # The pipx task from the page, under the test name, with the venv's repo-traffic on PATH.
    out("$ (the Register-ScheduledTask block on the Scheduling page, task name %s)" % TEST_TASK)
    script = (
        ("$env:PATH = '%s;' + $env:PATH\n" % info["scripts"])
        + PIPX_TASK.strip().replace("-TaskName repo-traffic", "-TaskName " + TEST_TASK)
        + " | Out-Null"
    )
    p = ps(script)
    if p.returncode:
        out("exit %d: %s" % (p.returncode, mask(p.stderr.strip())))
        return
    out("read back:")
    out(mask(ps(TASK_READBACK % TEST_TASK).stdout.rstrip()))
    ps("Unregister-ScheduledTask -TaskName '%s' -Confirm:$false" % TEST_TASK)
    out(
        "removed: %s"
        % (
            "yes"
            if not ps("Get-ScheduledTask -TaskName '%s' -ErrorAction SilentlyContinue" % TEST_TASK).stdout.strip()
            else "NO"
        )
    )


def schedule_files(scratch, info):
    section("scheduling: unit files, plist and cron line")
    folder = scratch / "schedule"
    folder.mkdir(exist_ok=True)
    (folder / "repo-traffic.service").write_text(SYSTEMD_SERVICE, encoding="utf-8", newline="\n")
    (folder / "repo-traffic.timer").write_text(SYSTEMD_TIMER, encoding="utf-8", newline="\n")
    out("--- repo-traffic.service")
    out(SYSTEMD_SERVICE.rstrip("\n"))
    out("--- repo-traffic.timer")
    out(SYSTEMD_TIMER.rstrip("\n"))
    analyze = shutil.which("systemd-analyze")
    if analyze:
        # verify needs ExecStart to exist: check a copy that points at this venv's repo-traffic instead.
        check = folder / "check"
        check.mkdir(exist_ok=True)
        home = str(scratch / "home")
        Path(home, "repo-traffic-data").mkdir(parents=True, exist_ok=True)
        (check / "repo-traffic.service").write_text(
            SYSTEMD_SERVICE.replace("%h/.local/bin/repo-traffic", info["scripts"] + "/repo-traffic").replace(
                "%h", home
            ),
            encoding="utf-8",
        )
        (check / "repo-traffic.timer").write_text(SYSTEMD_TIMER, encoding="utf-8")
        p = subprocess.run(
            [analyze, "--user", "verify", str(check / "repo-traffic.timer"), str(check / "repo-traffic.service")],
            capture_output=True,
            text=True,
        )
        out(
            "systemd-analyze --user verify: exit %d%s"
            % (p.returncode, (": " + mask(p.stderr.strip())) if p.stderr.strip() else ", no messages")
        )
        p = subprocess.run([analyze, "calendar", "Mon *-*-* 09:00:00"], capture_output=True, text=True)
        norm = [x.strip() for x in p.stdout.splitlines() if "Normalized form" in x]
        out("systemd-analyze calendar: exit %d, %s" % (p.returncode, norm[0] if norm else p.stdout.strip()))
        out(
            "systemd: %s" % subprocess.run([analyze, "--version"], capture_output=True, text=True).stdout.split("\n")[0]
        )
    else:
        out("systemd-analyze: not on this machine (the Linux run checks the units)")
    plist = plistlib.loads(LAUNCHD_PLIST.encode("utf-8"))
    out("--- com.example.repo-traffic.plist")
    out(LAUNCHD_PLIST.rstrip("\n"))
    out(
        "plistlib parses it: Label %s, StartCalendarInterval %s"
        % (plist["Label"], json.dumps(plist["StartCalendarInterval"], sort_keys=True))
    )
    out("launchctl: not on this machine (not tested)")
    out("--- crontab line")
    out(CRON_LINE)
    out("cron: not run (it would edit the real crontab); not tested")


def gap_table():
    """The days between runs on the README's 1st-and-15th cron schedule, and whether repo-traffic warns."""
    import datetime

    section("scheduling: days between runs on the 1st and 15th, 2026-10 to 2027-10")
    runs = []
    for y, m in [(2026 + (10 + i - 1) // 12, (10 + i - 1) % 12 + 1) for i in range(13)]:
        runs += [datetime.date(y, m, 1), datetime.date(y, m, 15)]
    gaps = [(b, (b - a).days) for a, b in zip(runs, runs[1:])]
    over = [(b, d) for b, d in gaps if d > 14]
    out("runs: %d, gaps over 14 days (repo-traffic writes a gap line): %d" % (len(runs), len(over)))
    for b, d in over:
        out("  run on %s: %d days after the last" % (b, d))


def install_section(python, source, info, repo):
    section("installed")
    out("source: %s" % source)
    out(
        "repo-traffic %s (distribution %s), Python %s, %s %s"
        % (info["version"], info["dist"], info["python"], platform.system(), platform.machine())
    )
    out("runtime requirements: %s" % (info["requires"] or "none"))
    out("module: %s" % mask(info["file"]))
    tag = subprocess.run(["git", "-C", str(repo), "show", "v%s:repo_traffic.py" % VERSION], capture_output=True).stdout
    mine = Path(info["file"]).read_bytes()
    out(
        "installed repo_traffic.py equals the tag's: %s (sha256 %s)"
        % (
            hashlib.sha256(mine).hexdigest() == hashlib.sha256(tag.replace(b"\r\n", b"\n")).hexdigest()
            or hashlib.sha256(mine).hexdigest() == hashlib.sha256(tag).hexdigest(),
            hashlib.sha256(mine).hexdigest()[:16],
        )
    )
    out("lines in repo_traffic.py: %d" % len(mine.decode("utf-8").splitlines()))


def pipx_section(scratch):
    section("pipx install and uninstall (in the scratch folder)")
    venv = scratch / "venv-pipx"
    if venv.exists():
        shutil.rmtree(venv)
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py = str(venv / ("Scripts/python.exe" if WINDOWS else "bin/python"))
    subprocess.run([py, "-m", "pip", "install", "-q", "--disable-pip-version-check", "pipx"], check=True)
    env = dict(
        os.environ,
        PIPX_HOME=str(scratch / "pipx-home"),
        PIPX_BIN_DIR=str(scratch / "pipx-bin"),
        PIPX_MAN_DIR=str(scratch / "pipx-man"),
        PYTHONIOENCODING="utf-8",
    )
    for d in ("pipx-home", "pipx-bin", "pipx-man"):
        shutil.rmtree(scratch / d, ignore_errors=True)
    version = subprocess.run([py, "-m", "pipx", "--version"], capture_output=True, text=True, env=env).stdout.strip()
    out("pipx %s" % version)
    for cmd in (EXAMPLES["pipx"], EXAMPLES["pipx-uninstall"]):
        p = subprocess.run([py, "-m"] + cmd.split(), capture_output=True, text=True, env=env, encoding="utf-8")
        out("$ " + cmd)
        for line in (p.stdout + p.stderr).splitlines():
            keep = ("installed package", "These apps are", "- repo-traffic", "uninstalled", "done!")
            if any(k in line for k in keep):
                out(line.rstrip())
        out("$ echo $?")
        out(str(p.returncode))


def module_side_effects(info):
    data = Path(info["purelib"]) / "data"
    out("after python -m repo_traffic without --config, <site-packages> holds:")
    if data.exists():
        for line in tree([p.relative_to(data.parent).as_posix() for p in data.rglob("*") if p.is_file()]):
            out(line)
        shutil.rmtree(data)
        out("(removed by this program)")
    else:
        out("  no data folder")


def main_run(args):
    repo, scratch, python, source, info = setup()
    import harness

    install_section(python, source, info, repo)
    scripts = drivers(scratch, info)
    if os.environ.get("WIKI_VERIFY_PIPX"):
        pipx_section(scratch)
    for label, key in (
        ("version", "version"),
        ("module-version", "module-version"),
        ("help", "help"),
        ("top-no-value", "top-no-value"),
        ("abbreviation", "abbreviation"),
        ("unknown-flag", "unknown-flag"),
        ("top-not-a-number", "top-not-a-number"),
    ):
        real_case(label, EXAMPLES[key], python, info, scratch)
    cases = make_cases()
    for name, spec in cases.items():
        run_harness_case(harness, scripts, python, name, spec, spec["show"])
        if name == "module-no-config":
            module_side_effects(info)
    schedule_files(scratch, info)
    gap_table()
    if WINDOWS and os.environ.get("WIKI_VERIFY_TASKS"):
        tasks(repo, scratch, info)
    section("end")
    out("cases: %d harness, 7 commands" % len(cases))


# ---------------------------------------------------------------- --check-pages

FENCE = re.compile(r"^(\s*)(```+)\s*([\w#+-]*)\s*$")
CHECKED_LANGS = {"sh", "bash", "shell", "powershell", "pwsh", "ini", "xml", "json", "python", "cron", "crontab"}


def page_blocks(text):
    lines, i = text.split("\n"), 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        lang, start, body = m.group(3).lower(), i + 1, []
        i += 1
        while i < len(lines) and not lines[i].strip().startswith(m.group(2)):
            body.append(lines[i])
            i += 1
        i += 1
        yield start, lang, body


def program_text():
    """This program's lines and the lines of every string in it, stripped, as one searchable text."""
    import ast

    source = Path(__file__).read_text(encoding="utf-8")
    texts = [source] + [
        n.value for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    lines = []
    for t in texts:
        lines += [x.strip() for x in t.split("\n") if x.strip()] + [""]
    return "\n" + "\n".join(lines) + "\n"


def check_pages(wiki, out_file):
    """wikiwright's snippets skips shell blocks that only run commands, and reads no ini, xml or console
    commands; a command-line wiki is mostly those. This check reads them all: every non-comment line of a
    sh, powershell, ini, xml, json or python block must be a run of lines in this program or its strings,
    and every '$ ' command in a console block must be a command the saved output shows running, or in NOT_RUN."""
    known = program_text()
    ran = set()
    if out_file.exists():
        ran = {x[2:].strip() for x in out_file.read_text(encoding="utf-8").split("\n") if x.startswith("$ ")}
    commands = set(EXAMPLES.values()) | set(NOT_RUN)
    checked = missing = 0
    for page in sorted(Path(wiki).glob("*.md")):
        for start, lang, body in page_blocks(page.read_text(encoding="utf-8")):
            if lang in ("console",):
                for n, line in enumerate(body):
                    if line.startswith("$ "):
                        checked += 1
                        cmd = line[2:].strip()
                        if cmd not in ran and cmd not in NOT_RUN and cmd != "echo $?":
                            missing += 1
                            print("%s:%d: command not run by the program: %s" % (page.name, start + n + 1, cmd))
            elif lang in CHECKED_LANGS:
                want = [x.strip() for x in body if x.strip() and not x.strip().startswith("# ")]
                if not want:
                    continue
                checked += 1
                one = len(want) == 1 and (want[0] in commands or want[0] in ran)
                if want[0] in NOT_RUN:
                    print("%s:%d: not run (%s): %s" % (page.name, start, NOT_RUN[want[0]], want[0]))
                if not one and ("\n" + "\n".join(want) + "\n") not in known:
                    missing += 1
                    first = next((w for w in want if ("\n" + w + "\n") not in known), want[0])
                    print(
                        "%s:%d: %s block not in the program (first line not found: %s)"
                        % (page.name, start, lang, first[:70])
                    )
    print("check-pages: %d blocks and commands checked, %d missing" % (checked, missing))
    return 1 if missing else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-pages", metavar="WIKI")
    parser.add_argument("--out", default=str(HERE / "wiki-verify.out.txt"))
    args = parser.parse_args()
    if args.check_pages:
        return check_pages(args.check_pages, Path(args.out))
    main_run(args)
    Path(args.out).write_text("\n".join(LINES).lstrip("\n") + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
