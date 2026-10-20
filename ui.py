"""Shared helpers for app.py: data loading, Indian number format, chart styling."""
import base64
import json
import math
import re
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DATA = Path(__file__).parent / "data/processed"

# Colour tokens live in one place: styles/tokens.json (checked by check_theme.py).
TOKENS = json.loads((Path(__file__).parent / "styles" / "tokens.json").read_text(encoding="utf-8"))
_SERIES = {m: list(TOKENS[m]["series"]) for m in ("light", "dark")}  # 6 slots; a series keeps its slot on every tab
_THEME = {m: dict(TOKENS[m], mark_line=TOKENS[m]["card"], other=TOKENS[m]["zero"]) for m in ("light", "dark")}
for _t in _THEME.values():
    _t.pop("series", None)
SERIES = list(_SERIES["dark"])  # mutated in place by set_mode(), so `from ui import SERIES` stays current
THEME = dict(_THEME["dark"])
C = {}
TEXT2, GRID = THEME["text2"], THEME["grid"]


def set_mode(light):
    """Switch chart colours between the dark (default) and light palettes."""
    mode = "light" if light else "dark"
    SERIES[:] = _SERIES[mode]
    THEME.clear()
    THEME.update(_THEME[mode])
    s = SERIES
    C.clear()
    C.update({"revenue": s[0], "ebitda": s[1], "pat": s[2], "cfo": s[0], "capex": s[3], "fcf": s[2],
              "opm": s[1], "npm": s[2], "price": s[0], "ma50": s[1], "ma200": s[5]})
    global TEXT2, GRID
    TEXT2, GRID = THEME["text2"], THEME["grid"]


set_mode(False)


def rgba(hex_color, alpha):
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"


SECTION_ICON = {  # Material Symbols names (the icon font ships with Streamlit)
    "At a glance": "monitoring", "Latest quarter": "event_upcoming", "Share price": "candlestick_chart",
    "Financials": "bar_chart", "Growth and profitability": "trending_up", "Cash flow and financial health": "payments",
    "Dividends": "savings", "Balance sheet": "account_balance", "Profit flow": "account_tree",
}


def section(title, subtitle="", icon=None):
    """Large section header with an icon and a one-line description (stock-page style)."""
    ic = icon or next((v for k, v in SECTION_ICON.items() if title.startswith(k)), None)
    st.html(f'<div class="pc pc-section"><h2>'
            + (f'<span class="pc-ico" aria-hidden="true">{ic}</span>' if ic else "") + f"{escape(title)}</h2>"
            + (f"<p>{escape(subtitle)}</p>" if subtitle else "") + "</div>")


def sparkline(values, color, w=120, h=34, label=""):
    """Tiny inline SVG trend line (last point marked); gaps (NaN) are skipped."""
    pts = [(i, float(v)) for i, v in enumerate(values) if v is not None and pd.notna(v)]
    if len(pts) < 2:
        return ""
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    n = max(len(values) - 1, 1)
    xy = [(2 + i / n * (w - 4), h - 3 - ((v - lo) / ((hi - lo) or 1)) * (h - 6)) for i, v in pts]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    area = f"{xy[0][0]:.1f},{h} " + path + f" {xy[-1][0]:.1f},{h}"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
           f'<polygon points="{area}" fill="{color}" opacity="0.14"/>'
           f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" '
           f'stroke-linecap="round"/><circle cx="{xy[-1][0]:.1f}" cy="{xy[-1][1]:.1f}" r="3" fill="{color}"/></svg>')
    # st.html strips inline <svg>, so the sparkline travels as an image
    b64 = base64.b64encode(svg.encode()).decode()
    return f'<img class="pc-spark" src="data:image/svg+xml;base64,{b64}" width="{w}" height="{h}" alt="{escape(label)} trend">'


def count(value_text, v, dec=0):
    """A number that counts up when it first appears (see count_up_script); the final text is in the HTML."""
    return (f'<span class="pc-count" data-v="{v}" data-dec="{dec}">{escape(value_text)}</span>'
            if v is not None and pd.notna(v) else escape(value_text))


def count_up_script():
    """Animate .pc-count numbers once (0.7 s, ease-out, Indian digit grouping); skipped under reduced motion."""
    st.html("""<script>
(() => {
  if (window.__pcCount) return; window.__pcCount = true;
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const run = el => {
    if (el.dataset.done) return; el.dataset.done = 1;
    const end = parseFloat(el.dataset.v), dec = +el.dataset.dec || 0, txt = el.textContent;
    if (still || !isFinite(end)) return;
    const m = txt.match(/[-−]?[\\d,]+(\\.\\d+)?/); if (!m) return;
    const pre = txt.slice(0, m.index), post = txt.slice(m.index + m[0].length);
    const f = new Intl.NumberFormat('en-IN', {minimumFractionDigits: dec, maximumFractionDigits: dec});
    const t0 = performance.now();
    const step = t => { const k = Math.min(1, (t - t0) / 700), e = 1 - Math.pow(1 - k, 3);
      el.textContent = k < 1 ? pre + f.format(end * e) + post : txt; if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  };
  const scan = () => document.querySelectorAll('.pc-count:not([data-done])').forEach(run);
  scan(); new MutationObserver(scan).observe(document.body, {childList: true, subtree: true});
})();
</script>""", unsafe_allow_javascript=True)


GLOSSARY = {
    "TTM": "Trailing twelve months: the four latest quarters added up (here, to Sep'26).",
    "EBITDA": "Earnings before interest, tax, depreciation and amortisation: revenue minus operating costs.",
    "EBITDA margin": "EBITDA / revenue. Also called operating margin (OPM).",
    "PAT": "Profit after tax (net income).",
    "PBIT margin": "Segment profit before interest and tax / segment revenue.",
    "ROE": "Return on equity: PAT / (equity capital + reserves), year-end.",
    "ROCE": "Return on capital employed: EBIT / (equity + borrowings), year-end.",
    "DuPont": "ROE split into net margin × asset turnover × equity multiplier (total assets / equity).",
    "CFO": "Cash flow from operating activities.",
    "FCF": "Free cash flow as used here: CFO − capex + proceeds from fixed-asset sales.",
    "Cash conversion cycle": "Receivable days + inventory days − payable days.",
    "Acceptances": "Supplier bills paid by banks on the company's behalf; shown within trade payables.",
    "P/E": "Price / earnings per share (market cap / PAT).",
    "EV/EBITDA": "Enterprise value (market cap + borrowings − cash − current investments) / EBITDA.",
    "YoY / QoQ": "Change against the same period a year earlier / against the previous quarter.",
    "pp": "Percentage points: the difference between two percentages (12% → 14% is +2 pp).",
    "Inter-segment elimination": "Sales between segments, removed when segment revenue is consolidated.",
    "Promoter / FII / DII": "Founder group / foreign institutional investors / domestic institutional investors.",
}


def glossary(terms):
    """Plain-language definitions of the terms used on a tab."""
    with st.expander("Glossary"):
        st.markdown("\n".join(f"- **{t}**: {GLOSSARY[t]}" for t in terms if t in GLOSSARY))


def card(key):
    """A bordered chart card; styled by theme.css through its st-key-card-* class."""
    return st.container(border=True, key=f"card-{key}")


def filter_bar(where, title="Select period"):
    """Labelled filter strip near the top of a tab; styled by theme.css through its st-key-filterbar-* class."""
    box = st.container(key=f"filterbar-{where}")
    box.html(f'<div class="pc pc-filter-title">{escape(title)}</div>')
    return box


def synced(widget, name, where, label, default, **kw):
    """One logical filter shown in several places (sidebar and each tab's filter bar). Every copy has its own key;
    a change in any copy updates the shared value, and each copy is re-seeded from it before it is drawn."""
    shared, key = f"f_{name}", f"f_{name}__{where}"
    st.session_state.setdefault(shared, default)
    if type(st.session_state[shared]) is not type(default):  # e.g. a range slider must stay a (start, end) pair
        st.session_state[shared] = default
    st.session_state[key] = st.session_state[shared]
    return widget(label, key=key, on_change=lambda: st.session_state.update({shared: st.session_state[key]}), **kw)


def kv(label, value, note=""):
    """One key/value cell for kv_card (value may contain trusted HTML such as <small>)."""
    return (f'<div><div class="k">{escape(label)}</div><div class="v">{value}</div>'
            + (f'<div class="n">{escape(note)}</div>' if note else "") + "</div>")


def kv_card(title, cells, source_text="", cols=4):
    tag = _src_tag_html(source_text, title) if source_text else ""
    st.html(f'<div class="pc pc-card"><h3>{escape(title)}</h3><div class="pc-kv pc-kv-{cols}">{"".join(cells)}</div>'
            f'{tag}</div>')


def arrow(v, dec=2, suffix="%", prefix=""):
    """Signed change with an arrow, so direction never relies on colour: ▲ +1.20% / ▼ −0.44% / ■ 0.00%."""
    if v is None or pd.isna(v):
        return "n/a"
    if abs(v) < 0.5 * 10 ** -dec:
        return f"■ {prefix}{0:.{dec}f}{suffix}"
    s = f"{prefix}{abs(v):,.{dec}f}{suffix}"
    return f"▲ +{s}" if v > 0 else f"▼ −{s}"


# ---------------------------------------------------------------- source tags
# Every chart shows a short tag ("Source: Annual Report FY26"); the full note is in the ⓘ tooltip and is collected
# per tab for the "Sources & notes" expander at the bottom of the tab.
def _state():
    """Per-session register: {'tab': current tab, 'what': last chart title, 'src': {tab: [(what, tag, full)]}}."""
    return st.session_state.setdefault("_pc_src", {"tab": "Price chart", "what": "", "src": {}})


def reset_sources():
    st.session_state["_pc_src"] = {"tab": "Price chart", "what": "", "src": {}}


def begin_tab(name):
    s = _state()
    s["tab"], s["what"] = name, ""
    s["src"].setdefault(name, [])


def short_tag(text):
    """Short (<= ~40 char) source tag derived from the full source note."""
    t = text or ""
    ars = sorted(set(re.findall(r"Annual Reports? (?:FY\d\d–)?(FY\d\d)", t)) | set(re.findall(r"Annual Reports? (FY\d\d)–", t)))
    decks = sorted(set(re.findall(r"presentations? (Q\d FY\d\d)", t)))
    yf = "yfinance" in t
    if "Peer companies" in t:
        return "Source: Peer filings (unverified)"
    if ars and decks:
        tag = "Annual reports, presentations"
    elif ars:
        tag = f"Annual Report {ars[0]}" if len(ars) == 1 else f"Annual Reports {ars[0]}–{ars[-1]}"
    elif decks:
        tag = f"Investor presentation {decks[0]}" if len(decks) == 1 else "Investor presentations"
    elif yf:
        return "Source: NSE prices (yfinance)"
    elif "dashboard calculation" in t:
        return "Source: Company calls; dashboard calc"
    else:
        return "Source: Company results"
    if yf:
        return "Source: yfinance + company reports"
    return "Source: " + tag


def _register(full, what=""):
    s = _state()
    lst = s["src"].setdefault(s["tab"], [])
    item = (what or s["what"] or "Note", short_tag(full), full)
    if item not in lst:
        lst.append(item)


def _src_tag_html(full, what=""):
    _register(full, what)
    return (f'<div class="pc-srcline">{escape(short_tag(full))} <span class="pc-info" tabindex="0" '
            f'title="{escape(full)}" aria-label="Source details: {escape(full)}">ⓘ</span></div>')


def sources_expander(tabs=None, title="Sources & notes"):
    """One expander listing every full source note for the given tab(s) once."""
    s = _state()
    names = tabs or [s["tab"]]
    rows = [(n, w, f) for n in names for (w, _, f) in s["src"].get(n, [])]
    if not rows:
        return
    seen, lines_ = set(), []
    for n, w, f in rows:
        if f in seen:
            continue
        seen.add(f)
        lines_.append(f"- **{w}**{f' ({n})' if len(names) > 1 else ''}: {f}")
    with st.expander(title):
        st.markdown("\n".join(lines_))


def donut(labels, values, colors, title=None, center="", fmt=None, height=340):
    """Part-to-whole donut with direct labels (label + share) and formatted hover."""
    fmt = fmt or cr
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.62, sort=False, direction="clockwise",
        marker=dict(colors=colors, line=dict(color=THEME["mark_line"], width=2)),
        textinfo="percent", textposition="outside", textfont=dict(color=THEME["text"]),
        customdata=[fmt(v) for v in values], hovertemplate="%{label}: %{customdata} (%{percent})<extra></extra>"))
    fig.update_layout(
        title=dict(text=title, font=dict(size=15)) if title else None, height=height,
        margin=dict(l=10, r=10, t=50 if title else 20, b=10), paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color=THEME["text"]), showlegend=True,
        legend=dict(orientation="h", y=-0.08, yanchor="top", x=0.5, xanchor="center"),
        annotations=[dict(text=center, showarrow=False, font=dict(size=15, color=THEME["text"]))] if center else [])
    return fig


def _inv(hex_color):
    """Colour that becomes `hex_color` after the light-mode invert filter (exact for greys)."""
    h = hex_color.lstrip("#")
    return "#" + "".join(f"{255 - int(h[i:i + 2], 16):02x}" for i in (0, 2, 4))


def _token_css():
    """CSS variables from tokens.json: dark on :root, light inside re-inverted blocks, pre-inverted greys for the
    native (inverted) surfaces in light mode."""
    keys = ["page", "card", "border", "chip", "text", "text2", "muted", "grid", "up", "down", "accent"]
    dark = "; ".join(f"--{k}: {TOKENS['dark'][k]}" for k in keys)
    light = "; ".join(f"--{k}: {TOKENS['light'][k]}" for k in keys)
    inv = "; ".join(f"--inv-{k}: {_inv(TOKENS['light'][k])}" for k in ("page", "card", "border", "chip"))
    # widget colours (--w-*): dark tokens as is; in light mode the pre-image under the page filter, so they land on
    # the light tokens (exact for greys, close for tints); un-filtered pop-up layers use the light tokens directly
    wk = ["field", "field_border", "menu", "opt_hover", "accent", "text", "text2", "page", "card"]
    w_dark = "; ".join(f"--w-{k}: {TOKENS['dark'][k]}" for k in wk)
    w_light = "; ".join(f"--w-{k}: {_flt(TOKENS['light'][k])}" for k in wk)
    w_raw = "; ".join(f"--w-{k}: {TOKENS['light'][k]}" for k in wk)
    return (f":root {{ {dark}; {w_dark}; }}\n.stApp:has(.pc-light-flag) .pc {{ {light}; }}\n"
            f".stApp:has(.pc-light-flag) {{ {inv}; {w_light}; }}\n"
            f"body:has(.pc-light-flag) > :not(#root) {{ {w_raw}; }}\n")


def _flt(hex_color):
    """Colour that becomes `hex_color` after `invert(1) hue-rotate(180deg)` (the filter is its own inverse)."""
    h = hex_color.lstrip("#")
    r, g, b = (1 - int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    m = [(-0.574, 1.430, 0.144), (0.426, 0.430, 0.144), (0.426, 1.430, -0.856)]
    out = [min(1, max(0, a * r + b_ * g + c * b)) for a, b_, c in m]
    return "#" + "".join(f"{round(v * 255):02x}" for v in out)


def load_css():
    """Inject the token variables plus styles/theme.css (the single custom stylesheet)."""
    css = (Path(__file__).parent / "styles" / "theme.css").read_text(encoding="utf-8")
    st.html(f"<style>{_token_css()}{css}</style>")
WARN = "⚠️"
XLSX = "Polycab reported results"  # label for any figure not checked against a report or presentation
TTM = "TTM Sep-26"
OK = ("verified", "changed")
WIDE = ("annual", "quarterly", "balance_sheet", "cash_flow", "ratios_file")


@st.cache_data
def overrides():
    """Values checked against Polycab annual reports / presentations (verify_sources.py)."""
    p = DATA / "verified_overrides.csv"
    return pd.read_csv(p, dtype={"value": str, "period": str}) if p.exists() else pd.DataFrame(
        columns=["item", "period", "value", "unit", "source_file", "page", "previous_value", "status", "source_label",
                 "note", "target_file", "target_key"])


def _o(file):
    o = overrides()
    return o[o.target_file == file]


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _apply_wide(d, name):
    d = d.copy()
    for r in _o(name).itertuples():
        if r.period not in set(d.period):
            continue
        if r.target_key not in d.columns:
            d[r.target_key] = float("nan")
        m = d.period == r.period
        if r.status == "changed":
            d.loc[m, r.target_key] = _f(r.value)
        elif r.status == "not_found":  # an unverifiable, previously flagged value is hidden
            d.loc[m, r.target_key] = float("nan")
    if name == "quarterly" and "to_verify" in d.columns:
        done = set(_o("quarterly")[_o("quarterly").status.isin(OK) & (_o("quarterly").target_key == "revenue")].period)
        d.loc[d.period.isin(done), "to_verify"] = False
    if name == "balance_sheet":
        inv = d.investments.fillna(0)
        d["unclassified_assets_derived"] = d.unclassified_assets_derived - inv  # investments sat inside other assets
        if "non_controlling_interest" in d.columns:
            d["other_liabilities_ex_nci"] = d.liab_residual_derived - d.non_controlling_interest
    if name == "ratios_file":  # recompute ratios whose inputs were corrected
        a, b, c = load("annual").set_index("period"), load("balance_sheet").set_index("period"), load("cash_flow").set_index("period")
        idx = d.period
        pay = (b.trade_payables / a.material_cost * 365).reindex(idx).values
        rec = (b.trade_receivables / a.revenue * 365).reindex(idx).values
        inv = (b.inventories / a.material_cost * 365).reindex(idx).values
        d["payable_days"] = pay
        d["cash_conversion_cycle"] = rec + inv - pay
        cfo = c.cash_from_operating.reindex(idx).values
        d["cfo_to_pat"] = cfo / a.pat.reindex(idx).values * 100
        d["cfo_to_ebitda"] = cfo / a.operating_profit.reindex(idx).values * 100
    return d


def _apply_segments(d, name):
    d = d.copy()
    for r in _o(name).itertuples():
        seg, metric = r.target_key.split("|")
        m = (d.period == r.period) & (d.segment == seg) & (d.metric == metric)
        if r.status == "changed":
            d.loc[m, "value"] = _f(r.value)
        elif r.status == "not_found":
            d.loc[m, "value"] = float("nan")
        if "to_verify" in d.columns and r.status in OK:
            d.loc[m, "to_verify"] = False
    return d


def _apply_kpis(d):
    """KPI rows: a verified (kpi, period) replaces the old rows for that key; new verified rows are added."""
    d = d.copy()
    d["verified"] = False
    d["src_label"] = XLSX
    o = _o("kpis")
    keys = set(zip(o.target_key, o.period))
    d = d[[(k, p) not in keys for k, p in zip(d.kpi, d.period)]]
    cat = dict(zip(d.kpi, d.category))
    new = []
    for r in o.itertuples():
        v = str(r.value) if pd.notna(r.value) else ""
        lo = hi = val = float("nan")
        if "-" in v and not v.startswith("-"):
            lo, hi = (float(x) for x in v.split("-"))
        else:
            val = _f(v)
        new.append({"kpi": r.target_key, "category": cat.get(r.target_key, "Working capital"), "period": r.period,
                    "value": val, "value_low": lo, "value_high": hi, "unit": r.unit,
                    "note": r.note if pd.notna(r.note) else "", "verified": r.status in OK,
                    "src_label": r.source_label if r.status in OK else XLSX,
                    "source_section": r.source_label, "source_page": r.page})
    return pd.concat([d, pd.DataFrame(new)], ignore_index=True)


def _apply_expansions(d):
    d = d.copy()
    d["verified"] = False
    d["src_label"] = XLSX
    for r in _o("expansions").itertuples():
        m = d.event.str.contains(r.target_key, case=False, regex=False)
        if r.status in OK:
            d.loc[m, "verified"] = True
            d.loc[m, "src_label"] = r.source_label
            if r.unit == "date" and r.status == "changed":
                d.loc[m, "date"] = r.value
        if pd.notna(r.note) and r.note:
            d.loc[m, "note"] = r.note
    return d


@st.cache_data
def load(name):
    d = pd.read_csv(DATA / f"{name}.csv")
    if name in WIDE:
        return _apply_wide(d, name)
    if name in ("segments_y", "segments_q"):
        return _apply_segments(d, name)
    if name == "kpis":
        return _apply_kpis(d)
    if name == "expansions":
        return _apply_expansions(d)
    return d


def ok_periods(file, key):
    """Periods where this cell was verified (or corrected) against a report."""
    o = _o(file)
    return set(o[(o.target_key == key) & o.status.isin(OK)].period)


def cites(file, keys, periods):
    """Verified citations for these cells, e.g. ['Polycab Annual Report FY26, p.318', ...], plus count of unverified."""
    o = _o(file)
    keys = [keys] if isinstance(keys, str) else list(keys)
    o = o[o.target_key.isin(keys) & o.period.isin(list(periods)) & o.status.isin(OK)]
    labels = list(dict.fromkeys(o.source_label))
    covered = set(zip(o.target_key, o.period))
    missing = sum((k, p) not in covered for k in keys for p in periods)
    return labels, missing


def src(file, keys, periods, extra=""):
    """Source line text: verified documents, then 'Polycab reported results' for any unverified period."""
    labels, missing = cites(file, keys, periods)
    if not labels:
        text = XLSX
    else:
        shown = "; ".join(labels[:5]) + (f"; and {len(labels) - 5} more (see Verification table)" if len(labels) > 5 else "")
        text = shown + (f". Other periods: {XLSX}" if missing else "")
    return text + (f". {extra}" if extra else "")


def inr(x, dec=2, unit=""):
    """Indian digit grouping: 120942.06 -> 1,20,942.06. NaN -> n/a."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    neg, x = x < 0, abs(x)
    whole, frac = f"{x:.{dec}f}".split(".") if dec else (f"{x:.0f}", "")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    s = ",".join(groups + [tail]) + (f".{frac}" if frac else "")
    return ("-" if neg else "") + s + unit


def cr(x, dec=2):
    return "n/a" if x is None or pd.isna(x) else f"₹{inr(x, dec)} cr"


def pct(x, dec=1):
    return "n/a" if x is None or pd.isna(x) else f"{x:.{dec}f}%"


def source(text, what=""):
    """Short source tag under a chart; full note in the ⓘ tooltip and in the tab's Sources & notes expander."""
    st.html(f'<div class="pc">{_src_tag_html(text, what)}</div>')


def fy_of_quarter(q):
    """Dec'21 -> FY22, Mar'22 -> FY22 (Indian fiscal year ends March)."""
    mon, yy = q.split("'")
    yy = int(yy)
    return f"FY{yy if mon == 'Mar' else yy + 1:02d}"


def q_label(q):
    """Sep'26 -> Q2 FY27 (Apr–Jun = Q1)."""
    return f"Q{ {'Jun': 1, 'Sep': 2, 'Dec': 3, 'Mar': 4}[q.split(chr(39))[0]] } {fy_of_quarter(q)}"


_MON = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov",
                                     "Dec"], 1)}


def period_to_date(p):
    """Approximate plotting date for PDF period labels. FY = Apr-Mar; a quarter maps to its middle month.
    '9M FY24' -> end of Q3; ranges ('2011-2016') -> midpoint; '' -> None."""
    import re
    p = (p or "").replace(" call", "").strip()
    if not p:
        return None
    if m := re.fullmatch(r"(\d{4})-(\d{4})", p):
        return pd.Timestamp(year=(int(m[1]) + int(m[2])) // 2, month=7, day=1)
    if re.fullmatch(r"\d{4}(-\d{2}){0,2}", p):
        return pd.Timestamp(p + ("-07-01" if len(p) == 4 else "-15" if len(p) == 7 else ""))
    if m := re.fullmatch(r"([A-Z][a-z]{2}) (\d{4})", p):
        return pd.Timestamp(year=int(m[2]), month=_MON[m[1]], day=15)
    if m := re.fullmatch(r"(?:Q([1-4])|9M) FY(\d{2})", p):
        q, fy = int(m[1] or 3), 2000 + int(m[2])
        month = {1: 5, 2: 8, 3: 11, 4: 2}[q]
        return pd.Timestamp(year=fy if q == 4 else fy - 1, month=month, day=15)
    if m := re.fullmatch(r"FY(\d{2})", p):
        return pd.Timestamp(year=1999 + int(m[1]), month=10, day=1)
    return None


FONT = dict(base=13, title=15, tick=12, legend=12)


def base_layout(fig, title=None, yaxis_title="₹ crore", height=380, ysuffix=""):
    """Shared chart layout. Title top-left; legend in its own row between title and plot (never over data);
    axis labels auto-margined; bar labels that do not fit are hidden instead of colliding."""
    fig.update_layout(
        title=dict(text=title, font=dict(size=FONT["title"]), x=0, xanchor="left", y=1, yref="container",
                   yanchor="top", pad=dict(t=8)) if title else None,
        height=height, margin=dict(l=10, r=10, t=64 if title else 36, b=10, autoexpand=True),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color=THEME["text"], size=FONT["base"]),
        legend=dict(orientation="h", x=0, xanchor="left", y=1.01, yanchor="bottom", title=None,
                    font=dict(size=FONT["legend"]), bgcolor="rgba(0,0,0,0)"),
        bargap=0.25, bargroupgap=0.08, barcornerradius=4, hovermode="x unified",  # hover label styled in show()
        uniformtext=dict(minsize=9, mode="hide"),
    )
    fig.update_xaxes(type="category", showgrid=False, linecolor=THEME["grid"], automargin=True,
                     tickfont=dict(color=THEME["text2"], size=FONT["tick"]))
    fig.update_yaxes(title=yaxis_title, gridcolor=THEME["grid"], zerolinecolor=THEME["zero"], automargin=True,
                     tickfont=dict(color=THEME["text2"], size=FONT["tick"]), title_font=dict(size=FONT["tick"]),
                     title_standoff=14,
                     tickformat={"": ",.0f", "x": ",.3~f"}.get(ysuffix, ",.1f"), ticksuffix=ysuffix)
    return fig


def indian_ticks(vmax, vmin=0.0, n=5, unit=""):
    """Tick values and Indian-grouped labels (1,20,000) for axes whose values exceed 99,999."""
    span = max(vmax - min(vmin, 0), 1)
    raw = span / (n - 1)
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.floor(min(vmin, 0) / step) * step
    vals = [start + i * step for i in range(int((vmax - start) / step) + 2)]
    return vals, [inr(v, 0) + unit for v in vals]


def wrap_label(s, width=14):
    """Break a long category label onto two lines at a space near the middle."""
    s = str(s)
    if len(s) <= width or " " not in s:
        return s
    mid = len(s) // 2
    cut = min((i for i, ch in enumerate(s) if ch == " "), key=lambda i: abs(i - mid))
    return s[:cut] + "<br>" + s[cut + 1:]


def bars(df, x, cols, names, colors, title=None, patterns=None, yaxis_title="₹ crore", fmt=None, ysuffix=""):
    """Grouped bars (default ₹ crore, Indian-format hover). patterns: pattern shape per x (e.g. to-verify)."""
    fmt = fmt or cr
    fig = go.Figure()
    for col, name, color in zip(cols, names, colors):
        fig.add_bar(
            x=df[x], y=df[col], name=name, marker_color=color,
            marker_line=dict(color=THEME["mark_line"], width=1),
            marker_pattern_shape=patterns, customdata=[fmt(v) for v in df[col]],
            hovertemplate=f"{name}: %{{customdata}}<extra></extra>",
        )
    fig = base_layout(fig, title, yaxis_title, ysuffix=ysuffix)
    vals = pd.concat([pd.to_numeric(df[c], errors="coerce") for c in cols])
    if vals.abs().max() >= 1e5:  # Plotly would print 120,000; use Indian grouping (1,20,000)
        tv, tt = indian_ticks(float(vals.max()), float(min(vals.min(), 0)))
        fig.update_yaxes(tickvals=tv, ticktext=tt)
    return fig


def lines(df, x, cols, names, colors, title=None, ysuffix="%", yaxis_title="%", fmt=pct, flag=None):
    """Lines with markers. flag = {col: [periods]}: those points leave the line and show as open ⚠ markers."""
    flag = flag or {}
    fig = go.Figure()
    for col, name, color in zip(cols, names, colors):
        bad = df[x].isin(flag.get(col, []))
        y = df[col].where(~bad)
        fig.add_scatter(
            x=df[x], y=y, name=name, mode="lines+markers", line=dict(color=color, width=2),
            marker=dict(size=8, line=dict(color=THEME["mark_line"], width=2)), customdata=[fmt(v) for v in y],
            hovertemplate=f"{name}: %{{customdata}}<extra></extra>", legendgroup=col,
        )
        if bad.any():
            fv = df.loc[bad, col]
            fig.add_scatter(
                x=df.loc[bad, x], y=fv, name=f"{name} {WARN} flagged", mode="markers+text", text=[WARN] * len(fv),
                textposition="top center", legendgroup=col,
                marker=dict(size=10, symbol="circle-open", color=color, line=dict(width=2)),
                customdata=[fmt(v) for v in fv], hovertemplate=f"{name} (flagged): %{{customdata}}<extra></extra>",
            )
    return base_layout(fig, title, yaxis_title, ysuffix=ysuffix)


def mult(x, dec=2):
    return "n/a" if x is None or pd.isna(x) else f"{x:.{dec}f}x"


def days(x):
    return "n/a" if x is None or pd.isna(x) else f"{x:.0f} days"


def _fit_labels(fig):
    """Avoid label collisions: wrap long category ticks onto two lines, and give a top legend enough room so it
    never runs into the title (rows estimated for the narrowest plot area in use)."""
    lay = fig.layout
    for ax in [k for k in lay.to_plotly_json() if k.startswith("xaxis")]:
        axis = lay[ax]
        if axis.type != "category" or axis.tickvals is not None:
            continue
        suffix = ax[5:]
        cats = []
        for tr in fig.data:
            if (getattr(tr, "xaxis", None) or "x") == "x" + suffix and getattr(tr, "x", None) is not None \
                    and getattr(tr, "orientation", "v") != "h":
                cats += [c for c in tr.x if isinstance(c, str) and c not in cats]
        if cats and any(len(c) > 8 and " " in c for c in cats):
            axis.update(tickvals=cats, ticktext=[wrap_label(c, 8) for c in cats])
    legend_on = lay.showlegend is not False and (lay.legend.y is None or lay.legend.y >= 1)
    names = [tr.name for tr in fig.data if tr.name and tr.showlegend is not False and tr.type != "pie"]
    if legend_on and len(names) > 1:
        px_needed = sum(44 + 7 * len(n) for n in names)
        rows = max(1, math.ceil(px_needed / 230))  # plot area of the narrowest cards
        has_title = bool(lay.title and lay.title.text)
        lay.margin.t = (36 if has_title else 8) + 26 * rows + 10
    ylabels = [str(v) for tr in fig.data if getattr(tr, "orientation", None) == "h" or tr.type == "scatter"
               for v in (tr.y if tr.y is not None and len(tr.y) and isinstance(tr.y[0], str) else [])]
    if ylabels:  # horizontal bars / lanes: reserve room for the longest category label
        lay.margin.l = max(lay.margin.l or 0, int(7 * max(len(v) for v in ylabels)) + 14)


HOVER_FONT = 14
HOVER_WRAP = 38  # characters per hover line, so a pop-up fits a 390px-wide phone chart


def _wrap_hover(s, width=HOVER_WRAP):
    """Break long hover lines at spaces (tags such as <b> are not counted)."""
    vis = lambda t: len(re.sub(r"<[^>]+>", "", t))
    out = []
    for seg in str(s).split("<br>"):
        line, rows = "", []
        for w in seg.split(" "):
            if line and vis(line + " " + w) > width:
                rows.append(line)
                line = w
            else:
                line = f"{line} {w}" if line else w
        out.append("<br>".join(rows + [line]))
    return "<br>".join(out)


def _fit_hover(fig):
    """Readable, never-truncated hover pop-ups: solid card fill, strong border, left-aligned, full trace names.
    Closest-point hovers on a period axis get a "FY26 | " prefix (unified hovers show the period as their header)."""
    fig.update_layout(hoverlabel=dict(bgcolor=THEME["card"], bordercolor=THEME["text2"], namelength=-1, align="left",
                                      font=dict(size=HOVER_FONT, color=THEME["text"])))
    fig.update_traces(hoverlabel=dict(namelength=-1, align="left"))
    if fig.layout.hovermode != "x unified" and fig.layout.xaxis.type == "category":
        for tr in fig.data:
            t = getattr(tr, "hovertemplate", None)
            if t and tr.type in ("bar", "scatter", "waterfall") and not re.search(r"%\{(x|y|label|text)", t) \
                    and getattr(tr, "orientation", "v") != "h":
                tr.hovertemplate = "%{x} | " + t
    for tr in fig.data:
        t = getattr(tr, "hovertemplate", None)
        if not t:
            continue
        lead = re.match(r"^(%\{x\} \| )?([^%<]{2,}?): %\{customdata\}", t)
        if lead and len(lead.group(2)) + 14 > HOVER_WRAP:  # "Long series name:<br>₹1,234.56 cr"
            tr.hovertemplate = t.replace(f"{lead.group(2)}: %{{customdata}}", f"{lead.group(2)}:<br>%{{customdata}}", 1)
        cd = getattr(tr, "customdata", None)
        if t.startswith("%{customdata}") and cd is not None and len(cd) and isinstance(cd[0], str):
            tr.customdata = [_wrap_hover(v) for v in cd]
    m = fig.layout.margin
    m.l, m.r = max(m.l or 0, 12), max(m.r or 0, 16)  # room so edge tooltips stay inside the chart


def show(fig, key=None, animate=False):
    """Render with the dashboard's own palette (theme=None), so light/dark text colours are never overridden.
    animate=True adds a 300 ms Plotly transition when the same chart (same key) gets new data."""
    fig.update_layout(template="none", font_family="Source Sans Pro, Source Sans 3, sans-serif",
                      font_color=THEME["text"], legend_font_color=THEME["text"])
    if animate:
        fig.update_layout(transition=dict(duration=300, easing="cubic-in-out"), uirevision=key or "keep")
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    _fit_labels(fig)
    _fit_hover(fig)
    t = fig.layout.title.text if fig.layout.title and fig.layout.title.text else ""
    if t:
        _state()["what"] = re.sub(r"<[^>]+>", " ", t)
    st.plotly_chart(fig, width="stretch", theme=None, key=key, config={"displaylogo": False})


_NUMLIKE = re.compile(r"^\s*([▲▼■]\s*)?[+\-−]?\s*(₹\s*)?[\d(]|^\s*n/a\s*$|^\s*$")


def table(df, **kw):
    """st.dataframe with numeric-looking columns right-aligned (values are often pre-formatted Indian strings)."""
    data = df.data if hasattr(df, "data") else df
    cfg = dict(kw.pop("column_config", {}) or {})
    for c in data.columns:
        vals = data[c].dropna().astype(str)
        if len(vals) and c not in cfg and vals.map(lambda v: bool(_NUMLIKE.match(v))).mean() >= 0.8 \
                and not vals.str.fullmatch(r"\s*").all():
            cfg[c] = st.column_config.Column(alignment="right")
    kw.setdefault("width", "stretch")
    st.dataframe(df, column_config=cfg or None, **kw)
