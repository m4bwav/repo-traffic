"""The golden test: the current script against the recording of 9b6e754.

Every case in tests/golden/cases.py runs through the same harness that
recorded the original. A run must equal the recording of this OS, except the
fields named in tests/golden/exceptions-<os>.json, each with the change id
(E1 to E7 in the plan) that the maintainer ruled on and the exact new value.
The test fails on an unlisted difference, on a listed field that no longer
differs, and on an unknown change id.

The exceptions files are made from this test's own difference list and then
reviewed: REPO_TRAFFIC_WRITE_EXCEPTIONS=1 pytest tests/test_golden.py writes
the file for this OS (and still fails, so a write is never a pass).
REPO_TRAFFIC_SCRIPT points the test at another copy of the script, such as
the one an installed wheel put in site-packages.
"""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden"
sys.path.insert(0, str(GOLDEN))
import harness  # noqa: E402
from cases import CASES  # noqa: E402

SCRIPT = Path(os.environ.get("REPO_TRAFFIC_SCRIPT") or ROOT / "repo_traffic.py")
RECORDING = json.loads((GOLDEN / ("recording-%s.json" % harness.platform_key())).read_text(encoding="utf-8"))
EXCEPTIONS_PATH = GOLDEN / ("exceptions-%s.json" % harness.platform_key())
CHANGE_IDS = {"E1", "E2", "E3", "E4", "E5", "E6", "E7"}
# Which ruled change explains each case's differences (the plan's exceptions table).
CASE_CHANGES = {
    "help-flag-runs-a-snapshot": ["E1"],
    "top-without-value": ["E1"],
    "npm-empty-body": ["E2", "E6"],
    "npm-429-every-time": ["E2", "E6"],
    "npm-search-404": ["E2", "E6"],
    "nuget-replica-503": ["E2", "E6"],
    "nuget-replica-unreachable": ["E2", "E6"],
    "no-push-access": ["E3", "E6", "E7"],
    "gh-login-fails-logs-to-default-data": ["E4"],
    "downloads-csv-old-header": ["E5", "E6"],
}


def flat(run):
    out = {k: v for k, v in run.items() if k != "files"}
    out.update({"files:" + p: c for p, c in run["files"].items()})
    return out


def differences(recorded, new):
    a, b = flat(recorded), flat(new)
    return {k: b.get(k) for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)}


def load_exceptions():
    if EXCEPTIONS_PATH.exists():
        return json.loads(EXCEPTIONS_PATH.read_text(encoding="utf-8"))
    return {}


@pytest.fixture(scope="module")
def results():
    return harness.run_cases(SCRIPT)


def test_recording_is_for_the_frozen_original():
    assert RECORDING["original"] == {"commit": "9b6e754", "blob": "ddb17b4414cad8ed1c7e98ea7869e63e30ee8675"}
    assert set(RECORDING["cases"]) == set(CASES)


def test_exceptions_name_ruled_changes_only():
    for case, runs in load_exceptions().items():
        assert case in CASES, case
        for entry in runs.values():
            assert entry["change"] and set(entry["change"]) <= CHANGE_IDS, (case, entry["change"])


def test_both_exception_files_cover_the_same_fields():
    files = [GOLDEN / "exceptions-windows.json", GOLDEN / "exceptions-posix.json"]
    if not all(f.exists() for f in files):
        pytest.skip("one exceptions file is missing")
    win, posix = (json.loads(f.read_text(encoding="utf-8")) for f in files)
    shape = [{c: {r: (e["change"], sorted(e["fields"])) for r, e in runs.items()} for c, runs in x.items()}
             for x in (win, posix)]
    assert shape[0] == shape[1]


@pytest.mark.parametrize("case", sorted(CASES))
def test_case_matches_recording_except_ruled_changes(case, results):
    if os.environ.get("REPO_TRAFFIC_WRITE_EXCEPTIONS"):
        pytest.skip("writing the exceptions file instead")
    listed = load_exceptions().get(case, {})
    for i, (recorded, new) in enumerate(zip(RECORDING["cases"][case], results[case])):
        diff = differences(recorded, new)
        entry = listed.get(str(i), {"change": [], "fields": {}})
        unlisted = {k: v for k, v in diff.items() if k not in entry["fields"]}
        assert not unlisted, "run %d differs from the recording in fields no exception names: %s" % (i, sorted(unlisted))
        stale = [k for k in entry["fields"] if k not in diff]
        assert not stale, "run %d: listed exceptions no longer differ: %s" % (i, stale)
        for k, v in entry["fields"].items():
            assert diff[k] == v, "run %d field %s differs from its ruled new value" % (i, k)
    assert len(results[case]) == len(RECORDING["cases"][case])


def test_write_exceptions(results):
    if not os.environ.get("REPO_TRAFFIC_WRITE_EXCEPTIONS"):
        pytest.skip("set REPO_TRAFFIC_WRITE_EXCEPTIONS=1 to write the exceptions file")
    out = {}
    for case in sorted(CASES):
        for i, (recorded, new) in enumerate(zip(RECORDING["cases"][case], results[case])):
            diff = differences(recorded, new)
            if diff:
                changes = CASE_CHANGES.get(case) or (["E6"] if all(k.endswith("/repos.csv") for k in diff) else ["UNRULED"])
                out.setdefault(case, {})[str(i)] = {"change": changes, "fields": diff}
    EXCEPTIONS_PATH.write_bytes(json.dumps(out, indent=1, sort_keys=True).encode("utf-8") + b"\n")
    pytest.fail("wrote %s: review it, then run again without the variable" % EXCEPTIONS_PATH.name)
