"""Record every snapshot with a timestamp and show the change over any window, in the console or a local page.

    python scripts/dashboard.py capture [--window 48h] [--top 10] [--no-snapshot]
    python scripts/dashboard.py summary [--window 48h] [--top 10]
    python scripts/dashboard.py serve [--port 8765] [--no-open]
    python scripts/dashboard.py build

- capture takes a snapshot (repo_traffic.py, a few minutes), records it and prints the summary.
- Recording adds each snapshot folder once to data/metrics.csv (one row per number, keyed by the UTC time its
  packages.json was written), so runs from the scheduled task or report.py are recorded too and the first run
  backfills every snapshot already saved. A second run on the same day overwrites that day's folder: record
  (capture, summary, serve, build all do) before running repo_traffic.py directly again the same day.
- Windows: Nh, Nd, last (since the previous capture), all. Repo views and clones and npm, PyPI and OpenUPM downloads
  come from daily counts (UTC days from the window's start day on); NuGet and release asset downloads, stars and
  forks are the latest capture minus the newest capture at or before the window's start.
- serve listens on 127.0.0.1 only; build writes data/dashboard.html. Everything stays in the data folder (gitignored).
"""

import argparse
import csv
import datetime as dt
import json
import re
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import repo_traffic as rt  # noqa: E402

METRICS_HEADER = ["captured_at", "source", "name", "metric", "value"]
DAILY_REGISTRIES = ("npm", "pypi", "openupm")
WINDOWS = ["last", "24h", "48h", "7d", "14d", "30d", "all"]
LABELS = {
    "last": "Since last capture",
    "24h": "24 hours",
    "48h": "48 hours",
    "7d": "7 days",
    "14d": "14 days",
    "30d": "30 days",
    "all": "All recorded",
}
STAMP = "%Y-%m-%dT%H:%M:%SZ"


def data_folder():
    cfg_path = ROOT / "repo_traffic.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    return ROOT / cfg.get("data", "data")


def stamp(path):
    return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).strftime(STAMP)


def parse_stamp(s):
    return dt.datetime.strptime(s, STAMP).replace(tzinfo=dt.timezone.utc)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_dirs(data):
    root = data / "snapshots"
    if not root.exists():
        return []
    return sorted(p for p in root.iterdir() if (p / "github.json").exists() and (p / "packages.json").exists())


def snapshot_rows(snapdir):
    g, p = read_json(snapdir / "github.json"), read_json(snapdir / "packages.json")
    rows = []
    for name, d in g.items():
        rows += [
            ("github", name, "stars", d["stars"]),
            ("github", name, "forks", d["forks"]),
            ("github", name, "release_downloads", rt.release_total(d)),
        ]
        for kind in ("views", "clones"):
            if d.get(kind):
                rows += [
                    ("github", name, kind + "_14d", d[kind]["count"]),
                    ("github", name, kind + "_uniques_14d", d[kind]["uniques"]),
                ]
    for reg in DAILY_REGISTRIES:
        for name, d in p.get(reg, {}).items():
            rows += [
                (reg, name, "last_14_days", sum(x["downloads"] for x in d["daily"])),
                (reg, name, "last_month", d["last_month"]),
            ]
    for name, d in p.get("nuget", {}).items():
        rows.append(("nuget", name, "total", d["total"]))
        if d.get("last_6_weeks") is not None:
            rows.append(("nuget", name, "last_6_weeks", d["last_6_weeks"]))
    return rows


def record(data):
    """Add every snapshot folder not yet in metrics.csv; returns the capture stamps added."""
    data.mkdir(parents=True, exist_ok=True)
    path = data / "metrics.csv"
    seen = set()
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            seen = {r["captured_at"] for r in csv.DictReader(f)}
    added = []
    new = not path.exists() or not path.stat().st_size
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(METRICS_HEADER)
        for snapdir in snapshot_dirs(data):
            at = stamp(snapdir / "packages.json")
            if at in seen:
                continue
            try:
                rows = snapshot_rows(snapdir)
            except (ValueError, KeyError, TypeError):
                continue  # half-written or unknown shape; a later run records the folder once it is whole
            w.writerows([at, *row] for row in rows)
            seen.add(at)
            added.append(at)
    return added


def load_metrics(data):
    series = {}
    path = data / "metrics.csv"
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                key = (r["source"], r["name"], r["metric"])
                series.setdefault(key, []).append((r["captured_at"], int(float(r["value"]))))
    for s in series.values():
        s.sort()
    captures = sorted({t for s in series.values() for t, _ in s})
    return captures, series


def load_repo_daily(data):
    out = {}
    path = data / "daily.csv"
    if path.exists():
        with path.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                keys = ("views", "views_uniques", "clones", "clones_uniques")
                out.setdefault(r["repo"], {})[r["date"][:10]] = tuple(int(r[k] or 0) for k in keys)
    return out


def load_package_daily(data):
    """{(registry, name): {day: downloads}}, merged over every snapshot; a later snapshot wins a day."""
    out = {}
    for snapdir in snapshot_dirs(data):
        try:
            p = read_json(snapdir / "packages.json")
        except ValueError:
            continue
        for reg in DAILY_REGISTRIES:
            for name, d in p.get(reg, {}).items():
                days = out.setdefault((reg, name), {})
                for x in d.get("daily", []):
                    days[x["day"][:10]] = x["downloads"]
    return out


def value_at(points, at):
    v = None
    for t, x in points:
        if t > at:
            break
        v = x
    return v


def window_bounds(window, captures, now):
    """(start of the window or None for all, the capture deltas are measured from)."""
    first = captures[0] if captures else None
    if window == "all":
        return None, first
    if window == "last":
        base = captures[-2] if len(captures) > 1 else first
        return (parse_stamp(base) if base else now), base
    m = re.fullmatch(r"(\d+)([hd])", window or "")
    if not m:
        raise ValueError("window must be Nh, Nd, last or all, not %r" % window)
    start = now - dt.timedelta(**{"hours" if m[2] == "h" else "days": int(m[1])})
    return start, max((c for c in captures if parse_stamp(c) <= start), default=first)


def compute(data, window, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    captures, series = load_metrics(data)
    start, base = window_bounds(window, captures, now)
    latest = captures[-1] if captures else None
    start_day = start.date().isoformat() if start else ""

    def current(key):
        s = series.get(key)
        return value_at(s, latest) if s else None

    def delta(key):
        s = series.get(key)
        if not s or latest is None:
            return None
        a, b = value_at(s, base), value_at(s, latest)
        return None if b is None else b - (s[0][1] if a is None else a)

    repo_daily = load_repo_daily(data)
    repos = []
    for name in sorted(set(repo_daily) | {k[1] for k in series if k[0] == "github"}):
        days = [v for d, v in repo_daily.get(name, {}).items() if d >= start_day]
        row = {
            "name": name,
            "visitors": sum(v[1] for v in days),
            "views": sum(v[0] for v in days),
            "cloners": sum(v[3] for v in days),
            "clones": sum(v[2] for v in days),
            "stars": current(("github", name, "stars")),
            "stars_delta": delta(("github", name, "stars")),
            "forks_delta": delta(("github", name, "forks")),
        }
        if row["views"] or row["clones"] or row["stars_delta"] or row["forks_delta"]:
            repos.append(row)
    repos.sort(key=lambda r: (-r["visitors"], -r["views"], -r["cloners"], r["name"]))

    packages = []
    for (reg, name), days in load_package_daily(data).items():
        n = sum(v for d, v in days.items() if d >= start_day)
        packages.append(
            {"registry": reg, "name": name, "downloads": n, "total": None, "through": max(days, default="")}
        )
    for (src, name, metric), _ in series.items():
        if (src, metric) == ("nuget", "total") or (src, metric) == ("github", "release_downloads"):
            total = current((src, name, metric))
            if src == "github" and not total:
                continue
            reg = "nuget" if src == "nuget" else "github-release"
            d = delta((src, name, metric))
            packages.append({"registry": reg, "name": name, "downloads": d, "total": total, "through": latest})
    packages.sort(key=lambda r: (-(r["downloads"] or 0), -(r["total"] or 0), r["registry"], r["name"]))

    span = (parse_stamp(latest) - parse_stamp(base)).total_seconds() / 3600 if latest and base else 0.0
    return {
        "window": window,
        "label": LABELS.get(window, window),
        "now": now.strftime(STAMP),
        "start_day": start_day or "the first day recorded",
        "base": base,
        "latest": latest,
        "span_hours": round(span, 1),
        "captures": len(captures),
        "repos": repos,
        "packages": packages,
    }


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    return out + ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]


def num(v, sign=False):
    if v is None:
        return "-"
    return ("+" if sign and v > 0 else "") + "{:,}".format(v)


def summary_text(w, top=10):
    if not w["latest"]:
        return "nothing recorded yet: run python scripts/dashboard.py capture"
    out = [
        "Window %s: daily counts from %s (UTC); capture deltas %s -> %s (%s h; %d captures recorded)"
        % (w["window"], w["start_day"], w["base"], w["latest"], w["span_hours"], w["captures"]),
        "",
        "Repos:",
    ]
    out += table(
        ["#", "repo", "visitors*", "views", "cloners*", "clones", "stars", "stars +/-"],
        [
            (
                i,
                r["name"],
                r["visitors"],
                r["views"],
                r["cloners"],
                r["clones"],
                num(r["stars"]),
                num(r["stars_delta"], True),
            )
            for i, r in enumerate(w["repos"][:top], 1)
        ],
    )
    out += ["* daily uniques added up: someone seen on two days counts twice", "", "Packages:"]
    out += table(
        ["#", "registry", "package", "downloads", "basis"],
        [
            (i, p["registry"], p["name"], num(p["downloads"]), "daily" if p["total"] is None else "captures")
            for i, p in enumerate([p for p in w["packages"] if p["downloads"]][:top], 1)
        ],
    )
    out.append("NuGet totals update in batches (flat for days, then a jump), so short-window NuGet deltas are lumpy")
    if w["span_hours"] == 0:
        out.append("(only one capture in range, so NuGet, release and star changes read as 0; capture again later)")
    return "\n".join(out)


def series_payload(data):
    _, series = load_metrics(data)
    repos, totals = {}, {}
    for name, days in load_repo_daily(data).items():
        ordered = sorted(days.items())
        repos[name] = {"views": [[d, v[0]] for d, v in ordered], "clones": [[d, v[2]] for d, v in ordered]}
        for d, v in ordered:
            t = totals.setdefault(d, [0, 0])
            t[0] += v[0]
            t[1] += v[2]
    packages = {
        "%s/%s" % k: {"label": "downloads per day", "points": sorted([d, n] for d, n in days.items())}
        for k, days in load_package_daily(data).items()
    }
    for (src, name, metric), s in series.items():
        if (src, metric) not in (("nuget", "total"), ("github", "release_downloads")):
            continue
        pts = []
        for (ta, va), (tb, vb) in zip(s, s[1:]):
            hours = (parse_stamp(tb) - parse_stamp(ta)).total_seconds() / 3600
            if hours > 0:
                pts.append([tb, round((vb - va) * 24 / hours, 1)])
        reg = "nuget" if src == "nuget" else "github-release"
        packages["%s/%s" % (reg, name)] = {"label": "downloads per day between captures", "points": pts}
    t = sorted(totals.items())
    return {
        "repos": repos,
        "packages": packages,
        "totals": {"views": [[d, v[0]] for d, v in t], "clones": [[d, v[1]] for d, v in t]},
    }


def render_html(data, live=False, now=None):
    payload = {
        "windows": {w: compute(data, w, now) for w in WINDOWS},
        "order": WINDOWS,
        "labels": LABELS,
        "default_window": "48h",
        "series": series_payload(data),
    }
    blob = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    return PAGE.replace("__DATA__", blob).replace("__LIVE__", "true" if live else "false")


def snapshot_now():
    """Run repo_traffic.py once; an error line, or None. Exit 1 is a partial run whose files are still written."""
    r = subprocess.run([sys.executable, str(ROOT / "repo_traffic.py")], capture_output=True, text=True, **rt.NO_WINDOW)
    return None if r.returncode == 0 else "snapshot exited %d; see data/run.log" % r.returncode


def capture(data):
    err = snapshot_now()
    return err, record(data)


def make_server(data, port):
    state = {"running": False, "message": ""}
    hosts = {"127.0.0.1:%d" % port, "localhost:%d" % port}

    def run():
        try:
            err, added = capture(data)
            state["message"] = err or "captured %s" % (", ".join(added) or "nothing new")
        except Exception as e:  # shown on the page; the server keeps running
            state["message"] = "capture failed: %r" % (e,)
        finally:
            state["running"] = False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, body, ctype="text/plain; charset=utf-8"):
            b = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def allowed(self):
            # The Host check stops DNS rebinding; the custom header makes a cross-site POST need a preflight we refuse.
            return self.headers.get("Host") in hosts

        def do_GET(self):  # noqa: N802
            if not self.allowed():
                return self.reply(403, "forbidden")
            if self.path == "/":
                record(data)
                return self.reply(200, render_html(data, live=True), "text/html; charset=utf-8")
            if self.path == "/status":
                return self.reply(200, json.dumps(state), "application/json")
            return self.reply(404, "not found")

        def do_POST(self):  # noqa: N802
            if not self.allowed() or self.headers.get("X-Capture") != "1":
                return self.reply(403, "forbidden")
            if self.path != "/capture":
                return self.reply(404, "not found")
            if not state["running"]:
                state.update(running=True, message="capturing")
                threading.Thread(target=run, daemon=True).start()
            return self.reply(202, json.dumps(state), "application/json")

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv=None):
    p = argparse.ArgumentParser(description="Record snapshots over time and show the change over a window.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("capture", "summary"):
        s = sub.add_parser(name)
        s.add_argument("--window", default="48h", help="Nh, Nd, last or all (default: 48h)")
        s.add_argument("--top", type=int, default=10, help="rows per table (default: 10)")
        if name == "capture":
            s.add_argument("--no-snapshot", action="store_true", help="record what is saved, take no new snapshot")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-open", action="store_true", help="do not open a browser")
    sub.add_parser("build")
    args = p.parse_args(argv)
    data = data_folder()
    if args.cmd in ("capture", "summary"):
        compute(data, args.window)  # reject a bad window before a snapshot runs for minutes
        if args.cmd == "capture" and not args.no_snapshot:
            err, _ = capture(data)
            if err:
                print(err)
        else:
            record(data)
        print(summary_text(compute(data, args.window), args.top))
        return 0
    if args.cmd == "build":
        record(data)
        out = data / "dashboard.html"
        out.write_text(render_html(data), encoding="utf-8")
        print(out)
        return 0
    record(data)
    server = make_server(data, args.port)
    url = "http://127.0.0.1:%d/" % args.port
    print("dashboard at %s (Ctrl+C stops it)" % url, flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>repo-traffic</title>
<style>
body{font:14px system-ui,sans-serif;margin:24px;background:#0f1420;color:#dde3ee}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:8px 0}
.meta,.muted{color:#8a96ab}.meta{margin:6px 0 14px}
button{background:#1d2638;color:#dde3ee;border:1px solid #33405a;border-radius:6px;padding:5px 11px;margin:0 4px 4px 0;
cursor:pointer}button.on{background:#3b6fd8;border-color:#3b6fd8}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}@media(max-width:1100px){.grid{grid-template-columns:1fr}}
table{border-collapse:collapse;width:100%}th,td{padding:4px 8px;border-bottom:1px solid #222c40;text-align:right}
th{cursor:pointer;color:#8a96ab;user-select:none}.l{text-align:left}
tr.row:hover{background:#18213a;cursor:pointer}tr.sel{background:#22315a}.pos{color:#6fd38a}.neg{color:#e07070}
#chart{background:#131a2a;border-radius:8px;padding:12px;margin:14px 0}
</style></head><body>
<h1>repo-traffic</h1>
<div id="wins"></div><button id="capbtn" hidden>Capture now</button> <span id="cap" class="muted"></span>
<div class="meta" id="meta"></div>
<div id="chart"><div id="ctitle" class="muted"></div><svg id="svg" width="100%" height="230"></svg></div>
<div class="grid">
<div><h2>Repos</h2><table id="repos"></table>
<p class="muted">Visitors and cloners add up each day's uniques, so someone seen on two days counts twice.
Stars change is between captures.</p></div>
<div><h2>Packages</h2><table id="packages"></table>
<p class="muted">npm, PyPI, OpenUPM: daily counts. NuGet and release assets: latest capture minus the capture at the
window's start (Total is all time; NuGet updates its totals in batches, so short windows are lumpy).</p></div></div>
<script>
const D=__DATA__,LIVE=__LIVE__,$=id=>document.getElementById(id);
const COLS={repos:[["name","Repo"],["visitors","Visitors"],["views","Views"],["cloners","Cloners"],["clones","Clones"],
["stars","Stars"],["stars_delta","Stars +/-"]],packages:[["registry","Registry"],["name","Package"],
["downloads","Downloads"],["total","Total"]]};
const sort={repos:["visitors",-1],packages:["downloads",-1]};let win=D.default_window,sel=null;
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function num(v,d){if(v==null)return'<span class="muted">-</span>';const s=v.toLocaleString();
return d&&v>0?'<span class="pos">+'+s+"</span>":d&&v<0?'<span class="neg">'+s+"</span>":s}
function rowId(kind,r){return kind+":"+(r.registry?r.registry+"/":"")+r.name}
function renderWins(){$("wins").innerHTML=D.order.map(w=>`<button class="${w===win?"on":""}" data-w="${w}">`+
`${D.labels[w]}</button>`).join("");document.querySelectorAll("#wins button").forEach(b=>b.onclick=()=>{
win=b.dataset.w;render()})}
function renderTable(kind){const W=D.windows[win],[k,dir]=sort[kind],rows=[...W[kind]];
rows.sort((a,b)=>{const x=a[k],y=b[k];if(typeof x==="string"||typeof y==="string")
return dir*String(x).localeCompare(String(y));return dir*((x??-1e18)-(y??-1e18))});
let h="<tr>"+COLS[kind].map(([c,t])=>`<th data-k="${c}" class="${c==="name"||c==="registry"?"l":""}">${t}`+
`${c===k?(dir<0?" &#9660;":" &#9650;"):""}</th>`).join("")+"</tr>";
for(const r of rows){const id=rowId(kind,r);h+=`<tr class="row ${id===sel?"sel":""}" data-id="${esc(id)}">`+
COLS[kind].map(([c])=>typeof r[c]==="string"?`<td class="l">${esc(r[c])}</td>`:`<td>${num(r[c],c.endsWith("_delta"))}</td>`)
.join("")+"</tr>"}
if(!rows.length)h+=`<tr><td class="l muted" colspan="9">nothing in this window</td></tr>`;
const t=$(kind);t.innerHTML=h;t.querySelectorAll("th").forEach(th=>th.onclick=()=>{const c=th.dataset.k;
sort[kind]=[c,sort[kind][0]===c?-sort[kind][1]:(c==="name"||c==="registry"?1:-1)];renderTable(kind)});
t.querySelectorAll("tr.row").forEach(tr=>tr.onclick=()=>{sel=sel===tr.dataset.id?null:tr.dataset.id;render()})}
function chart(title,series){$("ctitle").textContent=title;const svg=$("svg"),W=svg.clientWidth||900,H=230,L=80,R=20,T=24,B=28;
const xs=[...new Set(series.flatMap(s=>s.points.map(q=>q[0])))].sort();
if(!xs.length){svg.innerHTML='<text x="10" y="40" fill="#6b7790">no data recorded yet</text>';return}
const t=x=>Date.parse(x.length===10?x+"T00:00:00Z":x),x0=t(xs[0]),x1=t(xs[xs.length-1]);
const ys=series.flatMap(s=>s.points.map(q=>q[1])),y0=Math.min(0,...ys),y1=Math.max(1,...ys);
const X=x=>L+(W-L-R)*(x1===x0?0.5:(t(x)-x0)/(x1-x0)),Y=y=>H-B-(H-T-B)*(y-y0)/(y1-y0||1);
const lab=(x,y,s,a)=>`<text x="${x}" y="${y}" fill="#6b7790" font-size="11" text-anchor="${a}">${esc(s)}</text>`;
let g=`<line x1="${L}" y1="${H-B}" x2="${W-R}" y2="${H-B}" stroke="#33405a"/>`+lab(L,H-B+16,xs[0].slice(0,16),"start")+
lab(W-R,H-B+16,xs[xs.length-1].slice(0,16),"end")+lab(L-6,Y(y1)+4,y1.toLocaleString(),"end")+
lab(L-6,Y(y0)+4,y0.toLocaleString(),"end");
series.forEach((s,i)=>{const p=[...s.points].sort((a,b)=>t(a[0])-t(b[0]));
g+=`<polyline fill="none" stroke="${s.color}" stroke-width="2" points="${p.map(q=>X(q[0])+","+Y(q[1])).join(" ")}"/>`+
p.map(q=>`<circle cx="${X(q[0])}" cy="${Y(q[1])}" r="3" fill="${s.color}"><title>${esc(s.name)} ${esc(q[0])}: `+
`${q[1].toLocaleString()}</title></circle>`).join("")+
`<text x="${W-R}" y="${14+i*14}" fill="${s.color}" font-size="12" text-anchor="end">${esc(s.name)}</text>`});svg.innerHTML=g}
function renderChart(){if(!sel){const s=D.series.totals;return chart("All repos: views and clones per day (UTC). Click a row"+
" to chart it.",[{name:"views",color:"#5b9cff",points:s.views},{name:"clones",color:"#f0a050",points:s.clones}])}
const kind=sel.slice(0,sel.indexOf(":")),id=sel.slice(sel.indexOf(":")+1),s=D.series[kind][id];
if(!s)return chart(id+": nothing to chart",[]);
if(kind==="repos")return chart(id+": views and clones per day (UTC)",[{name:"views",color:"#5b9cff",points:s.views},
{name:"clones",color:"#f0a050",points:s.clones}]);chart(id+": "+s.label,[{name:"downloads",color:"#6fd38a",points:s.points}])}
function render(){const W=D.windows[win];renderWins();
$("meta").textContent=W.latest?`${W.label}: daily counts from ${W.start_day} (UTC); capture changes ${W.base} to `+
`${W.latest} (${W.span_hours} h). ${W.captures} captures recorded.`:"Nothing recorded yet.";
renderTable("repos");renderTable("packages");renderChart()}
if(LIVE){const b=$("capbtn");b.hidden=false;const poll=()=>fetch("/status").then(r=>r.json()).then(s=>{
$("cap").textContent=s.message;if(s.running)setTimeout(poll,4000);else if(s.message.startsWith("captured"))location.reload()});
b.onclick=()=>{b.disabled=true;$("cap").textContent="capturing (a few minutes)";
fetch("/capture",{method:"POST",headers:{"X-Capture":"1"}}).then(()=>setTimeout(poll,4000))}}
render();
</script></body></html>
"""

if __name__ == "__main__":
    sys.exit(main())
