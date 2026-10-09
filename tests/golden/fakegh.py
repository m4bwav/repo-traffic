"""The golden harness's stand-in for the GitHub CLI.

The harness installs it as an executable named gh (gh.exe on Windows) in a
folder it puts first on PATH. Each call appends its arguments as one JSON
line to GOLDEN_GH_LOG and answers from GOLDEN_GH_FIXTURE, a JSON object
keyed by the arguments joined with single spaces:

  {"api user -q .login": {"stdout": "octo-example\\n"},
   "api repos/o/r/traffic/views?per=day": {"code": 1, "stderr": "gh: ... (HTTP 403)\\n"}}

A value with a "json" member is printed as that JSON. A call with no entry
exits 1 with "fake gh: no fixture for ..." on stderr, like a gh error.
Standard library only.
"""
import json
import os
import sys


def main():
    args = sys.argv[1:]
    with open(os.environ["GOLDEN_GH_LOG"], "a", encoding="utf-8") as f:
        f.write(json.dumps(args) + "\n")
    with open(os.environ["GOLDEN_GH_FIXTURE"], encoding="utf-8") as f:
        fixture = json.load(f)
    answer = fixture.get(" ".join(args))
    if answer is None:
        sys.stderr.write("fake gh: no fixture for " + " ".join(args) + "\n")
        return 1
    out = json.dumps(answer["json"]) + "\n" if "json" in answer else answer.get("stdout", "")
    sys.stdout.buffer.write(out.encode("utf-8"))
    sys.stderr.buffer.write(answer.get("stderr", "").encode("utf-8"))
    return answer.get("code", 0)


if __name__ == "__main__":
    sys.exit(main())
