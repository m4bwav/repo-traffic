"""Runs a repo_traffic script through the golden cases and records what it did.

run_cases(script) copies the script into a fresh folder per case (so the
folder plays the clone: repo_traffic.json and data/ sit next to it), starts a
local HTTP server for the case's npm and NuGet answers, puts the fake gh
first on PATH, and runs the script through shim.py once per run. For each
run it records the exit code, stdout, the last line of stderr, every gh call,
every HTTP request the server saw, every sleep, and the text of every file
the script left in the folder. The work folder's path is replaced by <WORK>.

The capture (capture.py) runs it on the frozen original and writes the
recording; the golden test runs it on the current script and compares.
Standard library only.
"""
import http.server
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cases import CASES  # noqa: E402

SCRIPT_NAME = "repo_traffic.py"


def platform_key():
    return "windows" if sys.platform == "win32" else "posix"


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.answers, self.used, self.requests = {}, {}, []


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server's name)
        key = self.headers.get("X-Golden-Host", "?") + self.path
        self.server.requests.append({"url": key, "user_agent": self.headers.get("User-Agent")})
        answers = self.server.answers.get(key)
        if not answers:
            status, body = 404, b"golden harness: no fixture"
        else:
            i = self.server.used.get(key, 0)
            self.server.used[key] = i + 1
            a = answers[min(i, len(answers) - 1)]
            status = a["status"]
            body = (json.dumps(a["json"]) if "json" in a else a.get("body", "")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _install_fake_gh(bindir):
    """An executable named gh that runs fakegh.main with this Python."""
    bindir.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        # subprocess on Windows finds only .exe files on PATH; pip's launcher
        # builder makes one, as it does for every console script.
        from pip._vendor.distlib.scripts import ScriptMaker

        maker = ScriptMaker(None, str(bindir))
        maker.executable = sys.executable
        maker.variants = {""}
        maker.make("gh = fakegh:main")
    else:
        gh = bindir / "gh"
        gh.write_text("#!%s\nimport sys\nfrom fakegh import main\nsys.exit(main())\n" % sys.executable,
                      encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    found = shutil.which("gh", path=str(bindir))
    if not found or Path(found).resolve().parent != bindir.resolve():
        raise RuntimeError("fake gh not installed in " + str(bindir))


def _read_tree(work):
    files = {}
    for p in sorted(work.rglob("*")):
        rel = p.relative_to(work).as_posix()
        if p.is_dir() or rel in (SCRIPT_NAME, "repo_traffic.json") or "__pycache__" in rel:
            continue
        files[rel] = p.read_bytes().decode("utf-8", errors="backslashreplace")
    return files


def _normalize(text, work):
    for form in (str(work), work.as_posix(), str(work).replace("\\", "\\\\")):
        text = text.replace(form, "<WORK>")
    return text


def run_case(script, case, python=sys.executable):
    """Run every run of one case against script; return the list of records."""
    records = []
    with tempfile.TemporaryDirectory(prefix="rt-golden-") as tmp:
        tmp = Path(tmp).resolve()
        work, side = tmp / "clone", tmp / "harness"
        work.mkdir()
        side.mkdir()
        shutil.copyfile(script, work / SCRIPT_NAME)
        if case["config"] is not None:
            (work / "repo_traffic.json").write_text(json.dumps(case["config"]), encoding="utf-8")
        for rel, text in case["files"].items():
            (work / rel).parent.mkdir(parents=True, exist_ok=True)
            (work / rel).write_bytes(text.encode("utf-8"))
        _install_fake_gh(side / "bin")
        for n, r in enumerate(case["runs"]):
            server = _Server()
            server.answers = r["http"]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            fixture, ghlog, sleeps = side / ("gh-%d.json" % n), side / ("gh-%d.log" % n), side / ("sleep-%d" % n)
            fixture.write_text(json.dumps(r["gh"]), encoding="utf-8")
            ghlog.write_text("", encoding="utf-8")
            sleeps.write_text("", encoding="utf-8")
            env = {k: v for k, v in os.environ.items()
                   if k.upper() not in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "PYTHONPATH",
                                        "GH_TOKEN", "GITHUB_TOKEN")}
            env.update({
                "PATH": str(side / "bin") + os.pathsep + env.get("PATH", ""),
                "PYTHONPATH": str(HERE),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONDONTWRITEBYTECODE": "1",
                "GOLDEN_NOW": r["now"],
                "GOLDEN_SLEEPS": str(sleeps),
                "GOLDEN_SERVER": "127.0.0.1:%d" % server.server_address[1],
                "GOLDEN_DOWN": ",".join(r["down"]),
                "GOLDEN_GH_FIXTURE": str(fixture),
                "GOLDEN_GH_LOG": str(ghlog),
            })
            proc = subprocess.run([python, str(HERE / "shim.py"), str(work / SCRIPT_NAME), *r["args"]],
                                  cwd=str(work), env=env, capture_output=True, timeout=120)
            server.shutdown()
            server.server_close()
            stderr = proc.stderr.decode("utf-8", errors="backslashreplace").strip().splitlines()
            records.append({
                "exit": proc.returncode,
                "stdout": _normalize(proc.stdout.decode("utf-8", errors="backslashreplace"), work),
                "stderr_last": _normalize(stderr[-1], work) if stderr else "",
                "gh_calls": [json.loads(line) for line in ghlog.read_text(encoding="utf-8").splitlines()],
                "requests": server.requests,
                "sleeps": [float(x) for x in sleeps.read_text(encoding="utf-8").split()],
                "files": {k: _normalize(v, work) for k, v in _read_tree(work).items()},
            })
    return records


def run_cases(script, names=None, python=sys.executable):
    return {name: run_case(script, CASES[name], python) for name in (names or CASES)}
