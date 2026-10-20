"""Peers & Ownership tab: peer snapshot vs industry median, shareholding trend."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui import table
from ui import card, donut
from ui import SERIES, THEME, XLSX, base_layout, bars, inr, lines, load, mult, pct, show, source

ME = "Polycab India"
PEERS = "Peer companies' reported results (not verified)"
METRICS = {  # column -> (label, unit, higher_is_better)
    "market_capitalization": ("Market cap", "cr", None), "price_to_earnings": ("P/E", "x", None),
    "price_to_book_value": ("P/B", "x", None), "ev_to_ebitda": ("EV/EBITDA", "x", None),
    "roe": ("ROE", "%", True), "roce": ("ROCE", "%", True), "opm": ("Operating margin", "%", True),
    "npm": ("Net margin", "%", True), "revenue_growth_3_years": ("Revenue growth, 3Y", "%", True),
    "pat_growth_3_years": ("PAT growth, 3Y", "%", True), "debt_to_equity": ("Debt / equity", "x", False),
}


def _fmt(v, unit):
    if pd.isna(v):
        return "n/a"
    return {"cr": f"₹{inr(v, 0)} cr", "x": mult(v, 2), "%": pct(v, 1)}[unit]


def _peer_bar(p, col, median):
    label, unit, _ = METRICS[col]
    d = p.dropna(subset=[col]).sort_values(col)
    fig = go.Figure()
    fig.add_bar(y=d.company, x=d[col], orientation="h",
                marker_color=[SERIES[0] if c == ME else THEME["other"] for c in d.company], marker_line=dict(color=THEME["mark_line"], width=1),
                customdata=[_fmt(v, unit) for v in d[col]], hovertemplate="%{y}: %{customdata}<extra></extra>",
                text=[_fmt(v, unit) for v in d[col]], textposition="outside", cliponaxis=False)
    fig.add_vline(x=median, line=dict(color=THEME["text2"], width=1, dash="dash"))
    fig.add_annotation(x=median, y=1, yref="paper", text=f"Industry median {_fmt(median, unit)}", showarrow=False,
                       xanchor="left", yanchor="bottom", font=dict(size=11, color=THEME["text2"]))
    fig = base_layout(fig, f"{label}: peers ranked (Polycab highlighted)", None, height=420)
    fig.update_yaxes(type="category", title=None, showgrid=False)
    fig.update_xaxes(type="linear", showgrid=True, gridcolor=THEME["grid"], title=None,
                     ticksuffix={"%": "%", "x": "x"}.get(unit, ""), tickformat=",.0f" if unit == "cr" else ",.1f")
    fig.update_layout(showlegend=False, hovermode="closest", margin=dict(r=60))
    return fig


def _peers():
    st.subheader(":material/groups: Peers vs industry median")
    raw = load("peers")
    med = raw[raw.is_industry_median.astype(bool)].iloc[0]
    p = raw[~raw.is_industry_median.astype(bool)].reset_index(drop=True)
    me = p[p.company == ME].iloc[0]

    cards = ["price_to_earnings", "roce", "roe", "opm", "revenue_growth_3_years", "debt_to_equity"]
    for box, col in zip(st.columns(len(cards)), cards):
        label, unit, better = METRICS[col]
        diff = me[col] - med[col]
        dtxt = f"{diff:+.2f}x vs median" if unit == "x" else f"{diff:+.1f} pp vs median"
        box.metric(label, _fmt(me[col], unit), dtxt,
                   delta_color="off" if better is None else ("normal" if better else "inverse"))

    col = st.selectbox("Metric", list(METRICS), index=5, format_func=lambda c: METRICS[c][0])
    c1, c2 = st.columns([3, 2])
    with c1:
        show(_peer_bar(p, col, med[col]))
        source(f"{PEERS} (undated snapshot). Dashed line = industry median.")
    with c2:
        # cross-check: the reported median equals the median of the listed peers (Polycab included)
        calc = {c: p[c].median() for c in METRICS}
        bad = [METRICS[c][0] for c in METRICS if abs(calc[c] - med[c]) > 0.01 * max(1, abs(med[c]))]
        st.markdown("**How the median is built**")
        st.caption(("✓ The industry median equals the median of the 10 listed companies (Polycab included) "
                    "for every metric." if not bad else f"⚠️ The industry median differs from the peers' median for: "
                    f"{', '.join(bad)}.") + " Missing values are skipped (V-Marc has no ROE/ROCE; Diamond Power has "
                   "no 3Y revenue growth).")
        st.caption("Diamond Power shows negative ROE and debt/equity (−4.20x), which points to negative equity; "
                   "it stretches the P/E, P/B and EV/EBITDA scales.")
        st.caption(f"Polycab's row is the peer snapshot at an undated price (market cap ₹{inr(me.market_capitalization, 0)} "
                   "cr). The Overview card uses the latest yfinance close instead.")

    t = pd.concat([p, med.to_frame().T]).reset_index(drop=True)
    out = pd.DataFrame({"Company": t.company})
    for c, (label, unit, _) in METRICS.items():
        out[label] = [_fmt(v, unit) for v in t[c]]
    styled = out.style.apply(lambda r: ["font-weight: 700" if r.Company == ME else
                                        ("font-style: italic" if r.Company == "Industry median"
                                         else "") for _ in r], axis=1)
    table(styled, hide_index=True, width="stretch", height=(len(out) + 1) * 35 + 3)  # all rows, no scroll
    source(f"{PEERS}. Growth = 3-year CAGR as reported.")


def _ownership(freq):
    st.subheader(":material/pie_chart: Shareholding")
    s = load("shareholding")
    want = "quarterly" if freq == "Quarterly" else "yearly"
    d = s[(s.freq == want)].dropna(subset=["promoter_pct"]).reset_index(drop=True)
    if d.empty:
        st.info("No shareholding data for this frequency.")
        return
    q = s[s.freq == "quarterly"].dropna(subset=["promoter_pct"]).reset_index(drop=True)
    last, yago = q.iloc[-1], (q.iloc[-5] if len(q) >= 5 else None)
    meta = dict(zip(load("meta").key, pd.to_numeric(load("meta").value, errors="coerce")))
    k = st.columns(5)
    for box, (col, label) in zip(k, [("promoter_pct", "Promoter"), ("fii_pct", "FII"), ("dii_pct", "DII"),
                                     ("public_pct", "Public")]):
        delta = None if yago is None else f"{last[col] - yago[col]:+.2f} pp vs {yago.period}"
        box.metric(f"{label}, {last.period}", pct(last[col], 2), delta, delta_color="off")
    k[4].metric("Promoter shares pledged", pct(meta.get("Pledged Percentage"), 1))

    c1, c2 = st.columns(2)
    with c1, card("ownership"):
        parts = [(n, last[c]) for c, n in [("promoter_pct", "Promoter"), ("fii_pct", "FII"), ("dii_pct", "DII"),
                                            ("public_pct", "Public"), ("government_pct", "Government")]
                 if pd.notna(last[c]) and last[c] > 0]
        show(donut([n for n, _ in parts], [v for _, v in parts], SERIES[:len(parts)], title=f"Ownership, {last.period}",
                   center=f"{last.no_of_shareholders / 1e5:.2f} lakh holders" if pd.notna(last.no_of_shareholders) else "",
                   fmt=lambda v: pct(v, 2)))
        source(f"{XLSX}, shareholding pattern (% of shares).")
    with c2, card("capital"):
        from tab_stock import _current, _prices
        cur, mcap = _current(_prices(), meta)
        cs = pd.DataFrame({"what": ["Market cap", "Enterprise value"], "v": [mcap, cur["ev"]]})
        fig = bars(cs, "what", ["v"], ["₹ crore"], [SERIES[0]], title="Capital structure at last close")
        fig.update_traces(marker_color=[SERIES[0], SERIES[2]])
        fig.update_layout(showlegend=False)
        show(fig)
        source("Price: yfinance. EV = market cap + borrowings − cash − current investments (Sep-26 investments: "
               f"Polycab investor presentation Q2 FY27, slide 15; borrowings and cash: {XLSX}). EV is below market "
               "cap because cash and investments exceed debt.")

    cols = [("promoter_pct", "Promoter"), ("fii_pct", "FII"), ("dii_pct", "DII"), ("public_pct", "Public")]
    if d.government_pct.fillna(0).abs().sum() > 0:
        cols.append(("government_pct", "Government"))
    c1, c2 = st.columns([3, 2])
    with c1:
        show(lines(d, "period", [c for c, _ in cols], [n for _, n in cols], SERIES[:len(cols)],
                   title=f"Shareholding pattern, {want} (% of shares)", fmt=lambda v: pct(v, 2)))
        source(f"{XLSX}. Government holding is 0 throughout and not drawn.")
    with c2:
        dd = d.dropna(subset=["no_of_shareholders"])
        fig = bars(dd, "period", ["no_of_shareholders"], ["Shareholders"], [SERIES[0]], title="Number of shareholders",
                   yaxis_title="holders", fmt=lambda v: inr(v, 0))
        fig.update_layout(showlegend=False)
        show(fig)
        source(XLSX)
    st.caption(f"Reported summary (undated): FII change over 1 year {meta.get('Change In FII Holdings 1 Year'):+.2f} pp, "
               f"DII {meta.get('Change In DII Holdings 1 Year'):+.2f} pp.")
    source(f"{XLSX} (reported shareholding summary, undated).", "Shareholding summary")


def render(freq):
    _peers()
    st.divider()
    _ownership(freq)
