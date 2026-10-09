# Golden recording of repo_traffic.py at 9b6e754

What the script did before the rewrite, recorded so the rewrite can be held to it. Nothing here touches the network: a fake `gh` answers GitHub, a local HTTP server answers npm and NuGet, and a socket guard refuses any address but 127.0.0.1. Every account, repository and package name in the fixtures is invented.

| File | What it is | Changes |
|---|---|---|
| `original/repo_traffic.py` | the script at commit 9b6e754, byte for byte (git blob `ddb17b4414cad8ed1c7e98ea7869e63e30ee8675`) | never |
| `cases.py` | the 18 cases: config, existing files, and each run's clock, arguments, gh answers and HTTP answers | never |
| `harness.py`, `shim.py`, `fakegh.py` | run a script through the cases and record exit code, stdout, the last stderr line, gh calls, HTTP requests, sleeps and every file written | never |
| `capture.py` | checks the blob id, records twice, compares, writes the recording; `--check` proves the recording still describes the original on this OS | never |
| `recording-windows.json`, `recording-posix.json` | the recordings (Python 3.14.6 on Windows x64, 3.14.4 on Linux x64) | never |

The recordings are never regenerated from new code. When the golden test fails, the fix goes in `repo_traffic.py`, or the difference becomes a named exception that the maintainer ruled on in the plan.

Re-check the recording against the original (any OS with Python 3.9 or later): `python tests/golden/capture.py --check`.
