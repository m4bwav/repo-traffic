"""Records the frozen original's behaviour on this OS: the golden recording.

Usage: python tests/golden/capture.py [--check]

Checks that original/repo_traffic.py is byte for byte the file at commit
9b6e754 (its git blob id), runs every case in cases.py against it twice,
fails if the two runs differ, and writes recording-<windows|posix>.json.
With --check it writes nothing and fails if the existing recording differs
from what the original does today (the recording is never regenerated once
committed; --check proves it still describes the original on this OS).
Standard library only; nothing leaves 127.0.0.1.
"""
import hashlib
import json
import platform
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness  # noqa: E402

ORIGINAL = HERE / "original" / "repo_traffic.py"
ORIGINAL_COMMIT = "9b6e754"
ORIGINAL_BLOB = "ddb17b4414cad8ed1c7e98ea7869e63e30ee8675"


def blob_id(path):
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def recording_path(key=None):
    return HERE / ("recording-%s.json" % (key or harness.platform_key()))


def main():
    if blob_id(ORIGINAL) != ORIGINAL_BLOB:
        sys.exit("original/repo_traffic.py is not the file at %s (blob %s)" % (ORIGINAL_COMMIT, ORIGINAL_BLOB))
    first = harness.run_cases(ORIGINAL)
    second = harness.run_cases(ORIGINAL)
    if first != second:
        diff = [n for n in first if first[n] != second[n]]
        sys.exit("two runs of the original differ in: " + ", ".join(diff))
    path = recording_path()
    if "--check" in sys.argv:
        recorded = json.loads(path.read_text(encoding="utf-8"))["cases"]
        if recorded != first:
            diff = [n for n in first if recorded.get(n) != first[n]]
            sys.exit("the original no longer matches %s in: %s" % (path.name, ", ".join(diff)))
        print("recording matches the original on this OS (%d cases)" % len(first))
        return
    out = {
        "original": {"commit": ORIGINAL_COMMIT, "blob": ORIGINAL_BLOB},
        "captured_with": {"python": platform.python_version(), "platform": harness.platform_key(),
                          "machine": platform.machine()},
        "cases": first,
    }
    path.write_bytes(json.dumps(out, indent=1, sort_keys=True).encode("utf-8") + b"\n")
    print("wrote %s: %d cases, recorded twice, identical" % (path.name, len(first)))


if __name__ == "__main__":
    main()
