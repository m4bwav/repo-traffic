"""Runs a repo_traffic script inside the golden harness's stand-in world.

Usage (the harness builds this command): python shim.py SCRIPT [ARGS...]

Before the script runs, this module:
- fixes the clock: date.today() and datetime.now() answer GOLDEN_NOW
  (ISO date-time, local and naive), so snapshot folders and run.log lines
  are the same on every run;
- records time.sleep() calls instead of sleeping, into GOLDEN_SLEEPS
  (one number per line), so retries and politeness waits are part of the
  recording and the capture does not take minutes;
- sends every https:// request to the harness's local HTTP server
  (GOLDEN_SERVER, host:port), with the original host in the X-Golden-Host
  header; hosts listed in GOLDEN_DOWN (comma-separated) fail with a
  connection error instead;
- refuses any socket connection to an address other than 127.0.0.1, so a
  recorded case can never reach a real API.

Then it runs SCRIPT as __main__ with sys.argv = [SCRIPT, *ARGS]. It changes
nothing in the script itself. Standard library only.
"""
import datetime as _real_dt
import os
import runpy
import socket
import sys
import time
import types
import urllib.error
import urllib.request

_NOW = _real_dt.datetime.fromisoformat(os.environ["GOLDEN_NOW"])


class _FakeDate(_real_dt.date):
    @classmethod
    def today(cls):
        return cls(_NOW.year, _NOW.month, _NOW.day)


class _FakeDateTime(_real_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        n = _NOW if tz is None else _NOW.replace(tzinfo=tz)
        return cls(n.year, n.month, n.day, n.hour, n.minute, n.second, n.microsecond, n.tzinfo)

    @classmethod
    def today(cls):
        return cls.now()


_dt = types.ModuleType("datetime")
_dt.__dict__.update({k: v for k, v in _real_dt.__dict__.items() if not k.startswith("__")})
_dt.date = _FakeDate
_dt.datetime = _FakeDateTime
sys.modules["datetime"] = _dt


def _sleep(seconds):
    with open(os.environ["GOLDEN_SLEEPS"], "a", encoding="utf-8") as f:
        f.write(f"{seconds}\n")


time.sleep = _sleep

_real_connect = socket.socket.connect


def _guarded_connect(self, address):
    host = address[0] if isinstance(address, tuple) else address
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise OSError(f"golden harness: connection to {host!r} refused (only 127.0.0.1 is allowed)")
    return _real_connect(self, address)


socket.socket.connect = _guarded_connect

_SERVER = os.environ["GOLDEN_SERVER"]
_DOWN = {h for h in os.environ.get("GOLDEN_DOWN", "").split(",") if h}


class _ToLocal(urllib.request.HTTPSHandler):
    def https_open(self, req):
        host = req.host
        if host in _DOWN:
            raise urllib.error.URLError(ConnectionRefusedError(10061, "golden harness: host down"))
        local = urllib.request.Request("http://" + _SERVER + req.selector, method=req.get_method())
        for k, v in req.header_items():
            local.add_header(k, v)
        local.add_header("X-Golden-Host", host)
        local.timeout = req.timeout
        return urllib.request.HTTPHandler().http_open(local)


urllib.request.install_opener(urllib.request.build_opener(_ToLocal))

if __name__ == "__main__":
    script = os.path.abspath(sys.argv[1])
    sys.argv = [script] + sys.argv[2:]
    sys.path[0] = os.path.dirname(script)
    runpy.run_path(script, run_name="__main__")
