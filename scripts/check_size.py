"""The size budget (plan D11): python scripts/check_size.py [WHEEL]

Lines of repo_traffic.py: green up to 600, yellow up to 800, red above.
Wheel size: green up to 25 KB, yellow up to 40 KB, red above.
Runtime dependencies in pyproject.toml: any is red.
Prints one line per measure; yellow prints a GitHub warning, red fails (exit 1).
WHEEL defaults to the newest dist/*.whl; without one, the wheel is skipped.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUDGET = {"lines": (600, 800), "wheel_kb": (25, 40)}


def grade(value, limits):
    return "green" if value <= limits[0] else "yellow" if value <= limits[1] else "red"


def main(argv):
    results = []
    lines = len((ROOT / "repo_traffic.py").read_text(encoding="utf-8").splitlines())
    results.append(("repo_traffic.py lines", lines, grade(lines, BUDGET["lines"]), "%d/%d" % BUDGET["lines"]))
    wheels = [Path(argv[0])] if argv else sorted((ROOT / "dist").glob("*.whl"), key=lambda p: p.stat().st_mtime)
    if wheels:
        kb = wheels[-1].stat().st_size / 1024
        results.append(("wheel KB", round(kb, 1), grade(kb, BUDGET["wheel_kb"]), "%d/%d" % BUDGET["wheel_kb"]))
    deps = re.search(r"^dependencies = \[(.*?)\]", (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M | re.S)
    count = len([d for d in re.findall(r'"([^"]+)"', deps.group(1))]) if deps else 0
    results.append(("runtime dependencies", count, "green" if count == 0 else "red", "0"))
    worst = "green"
    for name, value, colour, limits in results:
        print("%-22s %8s  %s (limits %s)" % (name, value, colour, limits))
        if colour == "yellow":
            print("::warning::size budget: %s is %s, in the yellow band (%s)" % (name, value, limits))
        if colour == "red" or (colour == "yellow" and worst == "green"):
            worst = colour
    return 1 if worst == "red" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
