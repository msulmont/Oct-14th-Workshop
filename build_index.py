"""
build_index.py: writes index.html, a one-page view of the research database.

Reads claims.json, sources.json, questions.md and REPORT.md (written by
verify.py) and builds a single self-contained page:

  - two charts comparing the companies quarter by quarter
    (FFO per share growth, and same store occupancy)
  - every verified claim, grouped by the question it answers,
    with its exact quote and a link to its source
  - held claims listed separately with the reason they were held

Only claims that REPORT.md marks "verified" are charted or listed as facts.
Run `python3 verify.py` first, then `python3 build_index.py`.

Python standard library only. Nothing in this file calls an AI model.
"""

import html
import json
import re
from pathlib import Path

HERE = Path(__file__).parent

COMPANIES = ["Essex", "AvalonBay", "Equity Residential"]
COMPANY_NOTES = {
    "Essex": "Core FFO · financial occupancy",
    "AvalonBay": "Core FFO · economic occupancy",
    "Equity Residential": "Normalized FFO · physical occupancy",
}
MONTH_TO_Q = {"3": 1, "6": 2, "9": 3, "12": 4,
              "March": 1, "June": 2, "September": 3, "December": 4}


def load(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def statuses():
    """claim_id -> (status, reason), read from the table in REPORT.md."""
    out = {}
    for line in (HERE / "REPORT.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        if len(cells) == 8 and re.fullmatch(r"c\d+", cells[0]):
            out[cells[0]] = ("verified" if cells[6] == "verified" else "held", cells[7])
    return out


def questions():
    text = (HERE / "questions.md").read_text(encoding="utf-8")
    topic = re.search(r"# Topic\s+(.+?)\s+#", text, re.S).group(1).strip()
    qs = {int(n): q.strip() for n, q in re.findall(r"^(\d+)\.\s+(.+)$", text, re.M)}
    return topic, qs


def company(claim):
    subject = claim["subject"]
    for name in COMPANIES:
        if subject.startswith(name):
            return name
    return "Other"


def question_for(claim):
    """The question number stored on the claim, if any."""
    q = claim.get("question")
    return int(q) if str(q).isdigit() else None


def quarter_key(claim):
    """'2026-Q2' for a quarterly series point, else None."""
    p, s = claim["period"], claim["subject"].lower()
    if "ffo per diluted share" in s and ("change vs. same quarter" in s or "growth, year over year" in s):
        m = re.match(r"Q([1-4]) (\d{4}) vs\.", p)
        return m and f"{m.group(2)}-Q{m.group(1)}"
    if "occupancy" in s:
        m = re.match(r"Quarter ended (\d+)/\d+/(\d{4})$", p) or \
            re.match(r"Quarter ended (March|June|September|December) \d+, (\d{4})$", p)
        return m and f"{m.group(2)}-Q{MONTH_TO_Q[m.group(1)]}"
    return None


def series(claims, kind):
    """{company: {quarter: claim}} for 'ffo' or 'occ', verified claims only.

    Only company-wide trend claims (question 9) are charted, so a market-level
    figure such as San Francisco occupancy never replaces a company's point.
    """
    out = {c: {} for c in COMPANIES}
    for c in claims:
        if question_for(c) != 9:
            continue
        s = c["subject"].lower()
        is_kind = ("occupancy" in s) if kind == "occ" else ("ffo" in s)
        k = quarter_key(c)
        if is_kind and k and company(c) in out:
            out[company(c)][k] = c
    return out


def main():
    claims = load("claims.json")
    sources = {s["id"]: s for s in load("sources.json")}
    status = statuses()
    topic, qs = questions()

    verified = [c for c in claims if status.get(c["claim_id"], ("held",))[0] == "verified"]
    held = [c for c in claims if c not in verified]

    def point(c):
        src = sources.get(c["source_id"], {})
        return {"v": float(c["value"]), "id": c["claim_id"], "quote": c["quote"],
                "src": src.get("title", c["source_id"]), "url": src.get("url", "")}

    ffo, occ = series(verified, "ffo"), series(verified, "occ")
    quarters = sorted({k for s in (ffo, occ) for co in s.values() for k in co})
    data = {
        "quarters": quarters,
        "companies": COMPANIES,
        "notes": COMPANY_NOTES,
        "ffo": {co: {k: point(c) for k, c in pts.items()} for co, pts in ffo.items()},
        "occ": {co: {k: point(c) for k, c in pts.items()} for co, pts in occ.items()},
    }

    # ---- claims grouped by question, then company
    groups = {}
    for c in verified:
        groups.setdefault(question_for(c), {}).setdefault(company(c), []).append(c)

    def claim_html(c):
        src = sources.get(c["source_id"], {})
        title = html.escape(src.get("title", c["source_id"]))
        link = f'<a href="{html.escape(src["url"])}">{title}</a>' if src.get("url") else title
        return (f'<li class="claim"><div class="claim-head"><span class="val">{html.escape(c["value"])}'
                f'<span class="unit"> {html.escape(c["unit"])}</span></span>'
                f'<span class="what">{html.escape(c["subject"])}</span>'
                f'<span class="when">{html.escape(c["period"])}</span></div>'
                f'<blockquote>{html.escape(c["quote"])}</blockquote>'
                f'<div class="src">{link} · <code>{html.escape(c["claim_id"])}</code></div></li>')

    def sort_key(c):
        k = quarter_key(c)
        return (k is None, k or "", int(c["claim_id"][1:]))

    sections = []
    for qn in sorted(groups, key=lambda q: (q is None, q or 0)):
        heading = f"Question {qn}: {qs[qn]}" if qn in qs else "Other verified claims"
        parts = []
        by_co = groups[qn]
        for co in COMPANIES + ["Other"]:
            if co not in by_co:
                continue
            items = sorted(by_co[co], key=sort_key)
            parts.append(f'<details{" open" if len(items) <= 8 else ""}><summary>{html.escape(co)} '
                         f'<span class="count">{len(items)} claims</span></summary>'
                         f'<ul class="claims">{"".join(claim_html(c) for c in items)}</ul></details>')
        sections.append(f'<section class="question"><h3>{html.escape(heading)}</h3>{"".join(parts)}</section>')

    unanswered = [f"<li>{html.escape(f'{n}. {q}')}</li>" for n, q in sorted(qs.items()) if n not in groups]

    if held:
        held_html = "<ul class=\"claims\">" + "".join(
            claim_html(c).replace('<div class="src">',
                                  f'<div class="reason">Held: {html.escape(status.get(c["claim_id"], ("held", "not checked yet"))[1] or "not checked yet")}</div><div class="src">')
            for c in held) + "</ul>"
    else:
        held_html = "<p class=\"muted\">None. Every claim passed the checker.</p>"

    page = TEMPLATE
    for key, val in {
        "%%TOPIC%%": html.escape(topic),
        "%%TOTAL%%": str(len(claims)),
        "%%VERIFIED%%": str(len(verified)),
        "%%HELD%%": str(len(held)),
        "%%SOURCES%%": str(len(sources)),
        "%%SECTIONS%%": "".join(sections),
        "%%UNANSWERED%%": ("<h3>Not answered yet</h3><ul class=\"plain\">" + "".join(unanswered) + "</ul>") if unanswered else "",
        "%%HELD_LIST%%": held_html,
        "%%DATA%%": json.dumps(data, ensure_ascii=False).replace("</", "<\\/"),
    }.items():
        page = page.replace(key, val)
    (HERE / "index.html").write_text(page, encoding="utf-8")
    print(f"Wrote index.html: {len(verified)} verified claims, {len(held)} held, {len(quarters)} quarters charted.")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>REIT Research Database</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #6f6d68;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: #e1e0d9; --quote: #f0efec;
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #9a988f;
    --grid: #2c2c2a; --axis: #383835; --border: #2c2c2a; --quote: #232321;
    --s1: #3987e5; --s2: #d95926; --s3: #199e70;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #9a988f;
  --grid: #2c2c2a; --axis: #383835; --border: #2c2c2a; --quote: #232321;
  --s1: #3987e5; --s2: #d95926; --s3: #199e70;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 1040px; margin: 0 auto; padding-block: 32px 64px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
h1, h2, h3 { text-wrap: balance; }
h1 { font-size: 28px; line-height: 1.2; margin: 0 0 6px; letter-spacing: -0.01em; }
h2 { font-size: 20px; margin: 40px 0 4px; }
h3 { font-size: 16px; margin: 28px 0 8px; }
p { margin: 0 0 10px; }
.lede { color: var(--ink-2); max-width: 70ch; }
.muted { color: var(--muted); }
.stats { display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0 8px; }
.stat { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; min-width: 130px; }
.stat b { display: block; font-size: 24px; font-variant-numeric: tabular-nums; }
.stat span { color: var(--ink-2); font-size: 13px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-top: 16px; }
.card h2 { margin-top: 0; }
.sub { color: var(--ink-2); font-size: 14px; margin-bottom: 12px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 4px 0 8px; font-size: 13px; color: var(--ink-2); }
.legend .key { display: inline-block; width: 18px; height: 2px; border-radius: 1px; vertical-align: middle; margin-right: 6px; }
.legend .note { color: var(--muted); }
.chart { position: relative; width: 100%; }
.chart svg { display: block; width: 100%; height: auto; overflow: visible; touch-action: pan-y; }
.chart svg:focus-visible { outline: 2px solid var(--s1); outline-offset: 4px; border-radius: 4px; }
.tip { position: absolute; pointer-events: none; background: var(--surface); border: 1px solid var(--axis);
  border-radius: 8px; padding: 8px 10px; font-size: 13px; box-shadow: 0 4px 16px rgba(0,0,0,.12);
  min-width: 170px; opacity: 0; z-index: 2; }
.tip .t { color: var(--ink-2); margin-bottom: 4px; }
.tip .row { display: flex; align-items: center; gap: 8px; white-space: nowrap; }
.tip .row b { font-variant-numeric: tabular-nums; min-width: 3.5em; }
.tip .row .k { width: 12px; height: 2px; border-radius: 1px; flex: none; }
.tip .row span { color: var(--ink-2); }
.notes { font-size: 13px; color: var(--ink-2); margin: 12px 0 0; padding-left: 18px; }
.notes li { margin: 2px 0; }
details { margin: 8px 0; }
summary { cursor: pointer; font-weight: 600; padding: 6px 0; }
summary .count { font-weight: 400; color: var(--muted); font-size: 13px; margin-left: 6px; }
.tablewrap { overflow-x: auto; }
table { border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; width: 100%; }
th, td { padding: 4px 10px; border-bottom: 1px solid var(--border); text-align: right; white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
th { color: var(--ink-2); font-weight: 600; }
ul.claims { list-style: none; padding: 0; margin: 0; }
.claim { border-top: 1px solid var(--border); padding: 12px 0; }
.claim-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 12px; }
.val { font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }
.unit { font-size: 13px; font-weight: 400; color: var(--ink-2); }
.what { color: var(--ink); }
.when { color: var(--muted); font-size: 13px; }
blockquote { margin: 6px 0; padding: 6px 10px; background: var(--quote); border-radius: 6px;
  font: 12.5px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--ink-2); overflow-wrap: anywhere; }
.src { font-size: 13px; color: var(--ink-2); }
.src a { color: inherit; }
.reason { font-size: 13px; font-weight: 600; margin-bottom: 2px; }
ul.plain { padding-left: 18px; color: var(--ink-2); }
footer { margin-top: 48px; font-size: 13px; color: var(--muted); }
code { font-size: 12px; }
</style>
</head>
<body>
<main>
<h1>REIT Research Database</h1>
<p class="lede">%%TOPIC%% Every number below comes from a saved company filing and was checked by <code>verify.py</code>: the source is unchanged, the quote is word for word in it, and the number is in the quote.</p>
<div class="stats">
  <div class="stat"><b>%%VERIFIED%%</b><span>verified claims</span></div>
  <div class="stat"><b>%%HELD%%</b><span>held claims</span></div>
  <div class="stat"><b>%%SOURCES%%</b><span>sources</span></div>
</div>
<p class="muted" style="font-size:13px">Verified means the number is really in the source. It doesn't prove it's the right number for the question, so spot-check against the PDFs.</p>

<div class="card">
  <h2>FFO per share growth</h2>
  <p class="sub">Change from the same quarter a year earlier, in percent. FFO (funds from operations) is the standard REIT earnings measure.</p>
  <div class="legend" id="legend-ffo"></div>
  <div class="chart" id="chart-ffo"></div>
  <ul class="notes">
    <li>Essex and AvalonBay report Core FFO; Equity Residential reports Normalized FFO. Both remove one-off items, but not exactly the same ones.</li>
    <li>Gaps are quarters where the filing printed no change as a dash ("—"), so there is no number to quote.</li>
  </ul>
  <details><summary>Show as a table</summary><div class="tablewrap" id="table-ffo"></div></details>
</div>

<div class="card">
  <h2>Same store occupancy</h2>
  <p class="sub">Percent, by quarter end. The scale starts at 92%, not zero, to show small changes.</p>
  <div class="legend" id="legend-occ"></div>
  <div class="chart" id="chart-occ"></div>
  <ul class="notes">
    <li>The measures differ. Essex reports financial occupancy and AvalonBay economic occupancy, both based on rent collected. Equity Residential reports physical occupancy, the share of units filled.</li>
    <li>AvalonBay's 2020 to Q1 2021 figures are for "Established Communities", its earlier name for same store properties.</li>
  </ul>
  <details><summary>Show as a table</summary><div class="tablewrap" id="table-occ"></div></details>
</div>

<h2>Verified claims by question</h2>
<p class="sub">Each claim shows the number, what it measures, the exact quote from the source and a link to the original document.</p>
%%SECTIONS%%
%%UNANSWERED%%

<h2>Held claims</h2>
%%HELD_LIST%%

<footer>Generated by <code>python3 build_index.py</code> from claims.json and REPORT.md (%%TOTAL%% claims). Do not edit by hand.</footer>
</main>

<script id="data" type="application/json">%%DATA%%</script>
<script>
(function () {
  const D = JSON.parse(document.getElementById("data").textContent);
  const COLORS = ["--s1", "--s2", "--s3"];
  const NS = "http://www.w3.org/2000/svg";
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const qLabel = k => k.slice(5) + " " + k.slice(0, 4);
  const fmt = (v, kind) => kind === "ffo" ? (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1) + "%" : v.toFixed(1) + "%";
  function el(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }

  function legend(id) {
    const box = document.getElementById(id);
    D.companies.forEach((co, i) => {
      const item = document.createElement("span");
      const key = document.createElement("span");
      key.className = "key"; key.style.background = "var(" + COLORS[i] + ")";
      item.appendChild(key);
      item.appendChild(document.createTextNode(co + " "));
      const note = document.createElement("span");
      note.className = "note"; note.textContent = "(" + D.notes[co] + ")";
      item.appendChild(note);
      box.appendChild(item);
    });
  }

  function table(id, kind) {
    const t = document.createElement("table");
    const head = t.createTHead().insertRow();
    ["Quarter"].concat(D.companies).forEach(h => { const th = document.createElement("th"); th.textContent = h; head.appendChild(th); });
    const body = t.createTBody();
    D.quarters.forEach(q => {
      const r = body.insertRow();
      r.insertCell().textContent = qLabel(q);
      D.companies.forEach(co => {
        const p = D[kind][co][q];
        const c = r.insertCell();
        c.textContent = p ? fmt(p.v, kind) : "–";
        if (p) c.title = p.id + ": " + p.src;
      });
    });
    document.getElementById(id).appendChild(t);
  }

  function chart(id, kind, yMin, yMax, step) {
    const box = document.getElementById(id);
    const tip = document.createElement("div"); tip.className = "tip"; box.appendChild(tip);
    let idx = null, svg = null;

    function draw() {
      if (svg) svg.remove();
      const W = Math.max(320, box.clientWidth), narrow = W < 560;
      const H = narrow ? 260 : 320;
      const m = { t: 12, r: narrow ? 92 : 150, b: 28, l: 40 };
      const iw = W - m.l - m.r, ih = H - m.t - m.b;
      const n = D.quarters.length;
      const x = i => m.l + (n === 1 ? iw / 2 : i * iw / (n - 1));
      const y = v => m.t + (yMax - v) / (yMax - yMin) * ih;
      svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", tabindex: "0",
        "aria-label": (kind === "ffo" ? "FFO per share growth" : "Same store occupancy") + " by quarter for " + D.companies.join(", ") + ". Use left and right arrow keys to read values." });
      box.insertBefore(svg, tip);

      for (let v = yMin; v <= yMax + 1e-9; v += step) {
        const zero = kind === "ffo" && Math.abs(v) < 1e-9;
        el("line", { x1: m.l, x2: m.l + iw, y1: y(v), y2: y(v), stroke: css(zero ? "--axis" : "--grid"), "stroke-width": zero ? 1.5 : 1 }, svg);
        const t = el("text", { x: m.l - 8, y: y(v) + 4, "text-anchor": "end", fill: css("--muted"), "font-size": 11 }, svg);
        t.textContent = (kind === "ffo" && v > 0 ? "+" : "") + v + "%";
      }
      D.quarters.forEach((q, i) => {
        if (!q.endsWith("Q1")) return;
        el("line", { x1: x(i), x2: x(i), y1: m.t + ih, y2: m.t + ih + 4, stroke: css("--axis") }, svg);
        if (narrow && +q.slice(0, 4) % 2) return;
        const t = el("text", { x: x(i), y: H - 8, "text-anchor": "start", fill: css("--muted"), "font-size": 11 }, svg);
        t.textContent = q.slice(0, 4);
      });

      const ends = [];
      D.companies.forEach((co, ci) => {
        const pts = D[kind][co], color = css(COLORS[ci]);
        let d = "", pen = false;
        D.quarters.forEach((q, i) => {
          const p = pts[q];
          if (!p) { pen = false; return; }
          d += (pen ? "L" : "M") + x(i).toFixed(1) + " " + y(p.v).toFixed(1);
          pen = true;
        });
        el("path", { d, fill: "none", stroke: css("--surface"), "stroke-width": 5, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
        el("path", { d, fill: "none", stroke: color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
        D.quarters.forEach((q, i) => {
          const p = pts[q], prev = pts[D.quarters[i - 1]], next = pts[D.quarters[i + 1]];
          if (p && !prev && !next) el("circle", { cx: x(i), cy: y(p.v), r: 3, fill: color }, svg);
        });
        const last = [...D.quarters].reverse().find(q => pts[q]);
        if (last) ends.push({ co, ci, y: y(pts[last].v), v: pts[last].v, i: D.quarters.indexOf(last) });
      });
      ends.sort((a, b) => a.y - b.y);
      for (let k = 1; k < ends.length; k++) ends[k].ly = Math.max(ends[k].y, (ends[k - 1].ly ?? ends[k - 1].y) + 15);
      if (ends.length) ends[0].ly = ends[0].ly ?? ends[0].y;
      ends.forEach(e => {
        el("circle", { cx: x(e.i), cy: e.y, r: 4, fill: css(COLORS[e.ci]), stroke: css("--surface"), "stroke-width": 2 }, svg);
        const t = el("text", { x: x(e.i) + 10, y: e.ly + 4, fill: css("--ink"), "font-size": 12 }, svg);
        const b = el("tspan", { "font-weight": 600 }, t); b.textContent = fmt(e.v, kind);
        const s = el("tspan", { fill: css("--ink-2") }, t); s.textContent = " " + (narrow ? e.co.split(" ")[0] : e.co);
      });

      const hair = el("line", { y1: m.t, y2: m.t + ih, stroke: css("--axis"), "stroke-width": 1, visibility: "hidden" }, svg);
      const dots = D.companies.map((co, ci) => el("circle", { r: 4, fill: css(COLORS[ci]), stroke: css("--surface"), "stroke-width": 2, visibility: "hidden" }, svg));
      const hit = el("rect", { x: m.l - 10, y: m.t, width: iw + 20, height: ih, fill: "transparent" }, svg);

      function show(i) {
        idx = Math.max(0, Math.min(n - 1, i));
        const q = D.quarters[idx], X = x(idx);
        hair.setAttribute("x1", X); hair.setAttribute("x2", X); hair.setAttribute("visibility", "visible");
        tip.replaceChildren();
        const title = document.createElement("div"); title.className = "t"; title.textContent = qLabel(q); tip.appendChild(title);
        D.companies.forEach((co, ci) => {
          const p = D[kind][co][q];
          dots[ci].setAttribute("visibility", p ? "visible" : "hidden");
          if (p) { dots[ci].setAttribute("cx", X); dots[ci].setAttribute("cy", y(p.v)); }
          const row = document.createElement("div"); row.className = "row";
          const k = document.createElement("span"); k.className = "k"; k.style.background = "var(" + COLORS[ci] + ")";
          const b = document.createElement("b"); b.textContent = p ? fmt(p.v, kind) : "–";
          const s = document.createElement("span"); s.textContent = co + (p ? "" : " (no number)");
          row.append(k, b, s); tip.appendChild(row);
        });
        const scale = box.clientWidth / W;
        const left = X * scale, tw = tip.offsetWidth || 190;
        tip.style.left = (left + 12 + tw > box.clientWidth ? left - tw - 12 : left + 12) + "px";
        tip.style.top = (m.t * scale) + "px";
        tip.style.opacity = 1;
      }
      function hide() { idx = null; hair.setAttribute("visibility", "hidden"); dots.forEach(d => d.setAttribute("visibility", "hidden")); tip.style.opacity = 0; }
      function fromEvent(ev) {
        const r = svg.getBoundingClientRect();
        const px = (ev.clientX - r.left) * W / r.width;
        return Math.round((px - m.l) / (iw / (n - 1)));
      }
      hit.addEventListener("pointermove", ev => show(fromEvent(ev)));
      hit.addEventListener("pointerdown", ev => show(fromEvent(ev)));
      hit.addEventListener("pointerleave", hide);
      svg.addEventListener("blur", hide);
      svg.addEventListener("focus", () => show(idx ?? n - 1));
      svg.addEventListener("keydown", ev => {
        if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") { ev.preventDefault(); show((idx ?? n - 1) + (ev.key === "ArrowLeft" ? -1 : 1)); }
        if (ev.key === "Escape") hide();
      });
    }
    draw();
    let w = box.clientWidth;
    new ResizeObserver(() => { if (box.clientWidth !== w) { w = box.clientWidth; draw(); } }).observe(box);
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", draw);
    new MutationObserver(draw).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  }

  function bounds(kind, pad, step, floorMin, ceilMax) {
    const vals = D.companies.flatMap(co => Object.values(D[kind][co]).map(p => p.v));
    let lo = Math.floor((Math.min(...vals) - pad) / step) * step, hi = Math.ceil((Math.max(...vals) + pad) / step) * step;
    if (floorMin !== undefined) lo = Math.min(lo, floorMin);
    if (ceilMax !== undefined) hi = Math.max(hi, ceilMax);
    return [lo, hi];
  }

  legend("legend-ffo"); legend("legend-occ");
  table("table-ffo", "ffo"); table("table-occ", "occ");
  const [f0, f1] = bounds("ffo", 1, 10, 0, 0);
  chart("chart-ffo", "ffo", f0, f1, 10);
  const [o0, o1] = bounds("occ", 0.2, 1, 92, 97);
  chart("chart-occ", "occ", o0, o1, 1);
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
