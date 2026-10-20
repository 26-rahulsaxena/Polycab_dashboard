"""Expansions tab: timeline of plants, capex, orders, launches and corporate actions; capex; guidance tracker."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui import table
from ui import SERIES, THEME, XLSX, base_layout, bars, cr, filter_bar, inr, load, period_to_date, show, source, src

LANES = {  # entry category -> timeline lane (6 lanes, one fixed colour each)
    "Plant": "Plants and capacity", "Capacity addition": "Plants and capacity",
    "Capex programme": "Capex programmes", "Order": "Orders", "Launch": "Launches", "New business": "Launches",
    "Market expansion": "Markets", "Corporate": "Corporate actions", "Acquisition": "Corporate actions",
    "Divestment": "Corporate actions", "Merger": "Corporate actions", "Subsidiary": "Corporate actions",
}
LANE_ORDER = ["Plants and capacity", "Capex programmes", "Orders", "Launches", "Markets", "Corporate actions"]
LANE_COLOR = {}  # filled per run from the current palette
AR26, Q4_26 = "Polycab Annual Report FY26", "Polycab investor presentation Q4 FY26"


def _frame():
    e = load("expansions").copy()
    e["date"] = e["date"].fillna("")
    e["when"] = e["date"].map(period_to_date)
    e["lane"] = e.category.map(LANES).fillna("Corporate actions")
    e["src"] = e.src_label
    e["amount"] = [cr(v) if pd.notna(v) else "" for v in e.amount_cr]
    return e


def _timeline(e, y0, y1):
    d = e[e.when.notna() & (e.when.dt.year >= y0) & (e.when.dt.year <= y1)]
    fig = go.Figure()
    for lane in LANE_ORDER:
        x = d[d.lane == lane]
        if x.empty:
            continue
        hover = [f"<b>{r.event}</b><br>{r.date} · {r.category}"
                 + (f"<br>Amount: {r.amount} {r.amount_text or ''}" if r.amount else
                    (f"<br>{r.amount_text}" if isinstance(r.amount_text, str) and r.amount_text else ""))
                 + f"<br>Status: {r.status}<br>Source: {r.src}" for r in x.itertuples()]
        fig.add_scatter(x=x.when, y=x.lane, mode="markers", name=lane, customdata=hover,
                        marker=dict(size=13, color=LANE_COLOR[lane], symbol=["circle" if v else "circle-open" for v in x.verified],
                                    line=dict(color=LANE_COLOR[lane], width=2)),
                        hovertemplate="%{customdata}<extra></extra>")
    fig = base_layout(fig, "Timeline (filled = verified)", None, height=360)
    fig.update_xaxes(type="date", showgrid=True, gridcolor=THEME["grid"])
    fig.update_yaxes(type="category", categoryorder="array", categoryarray=LANE_ORDER[::-1], title=None,
                     ticksuffix="  ", showgrid=False)
    fig.update_layout(hovermode="closest", showlegend=False)
    return fig, len(d)


def _capex():
    k = load("kpis")
    co = k[(k.kpi == "Capex") & k.period.str.match(r"^FY\d{2}$") & k.verified].drop_duplicates("period")
    cf = load("cash_flow").set_index("period").capex_fixed_assets_purchased.abs()
    d = pd.DataFrame({"period": co.period.values, "company": co.value.values, "cf": [cf.get(p) for p in co.period]})
    fig = bars(d, "period", ["cf", "company"], ["Fixed-asset purchases (cash flow)", "Capex spends (company metric)"],
               [SERIES[0], SERIES[1]], title="Annual capex")
    fig.add_hrect(y0=1200, y1=1600, fillcolor=SERIES[3], opacity=0.15, line_width=0)
    fig.add_annotation(x=0, xref="paper", y=1600, text="Spring band ₹1,200–1,600 cr/yr",
                       showarrow=False, xanchor="left", yanchor="bottom", font=dict(size=11, color=THEME["text2"]))
    return fig, d, co


def _assessments():
    """Dashboard assessment: only for guidance items that verified figures can test. item_no -> (text, basis)."""
    a = load("annual").set_index("period")
    k = load("kpis")
    kv = lambda name, p: k[(k.kpi == name) & (k.period == p) & k.verified].value.squeeze()
    seg = load("segments_y")
    sv = lambda s, p, metric="revenue_cr": seg[(seg.segment == s) & (seg.period == p) & (seg.metric == metric)].value.squeeze()
    sm = lambda s: sv(s, "FY26", "pbit_margin_pct")
    m = {fy: a.operating_profit[fy] / a.revenue[fy] * 100 for fy in ["FY22", "FY23", "FY24", "FY25", "FY26"]}
    ex = {fy: kv("Export share of revenue", fy) for fy in ["FY23", "FY24", "FY25", "FY26"]}
    capex = {fy: kv("Capex", fy) for fy in ["FY23", "FY24", "FY25", "FY26"]}
    nwc = k[(k.kpi == "Net working capital days (company, closing)") & k.verified]
    epc = {fy: sv("EPC", fy) / a.revenue[fy] * 100 for fy in ["FY24", "FY25", "FY26"]}
    ar = "Polycab Annual Reports FY22–FY26 (consolidated P&L)"
    return {
        10: (f"FY26 capex ₹{inr(capex['FY26'], 0)} cr is inside the ₹1,200–1,600 cr annual band", f"{Q4_26}, slides 17 and 27"),
        11: (f"Payout {kv('Dividend payout ratio', 'FY24'):g}% (FY24) → {kv('Dividend payout ratio', 'FY25'):g}% (FY25) → "
             f"~{kv('Dividend payout ratio', 'FY26'):g}% (FY26): rising, still below 30%", f"{Q4_26}, slide 17"),
        16: ("Single digit in every year: " + ", ".join(f"{v:.1f}% ({fy})" for fy, v in epc.items())
             + " (gross EPC segment revenue / consolidated revenue)", "Polycab Annual Reports FY24–FY26, segment notes"),
        21: ("Exceeded: " + ", ".join(f"₹{inr(v, 0)} cr ({fy})" for fy, v in capex.items()),
             "Polycab investor presentations Q4 FY24–Q4 FY26"),
        22: ("Better than the range: " + ", ".join(f"{r.value:g} days ({r.period})" for r in nwc.itertuples())
             + " (closing basis)", "Polycab investor presentation Q2 FY27, slide 17"),
        25: (f"FY23 exports were {ex['FY23']:g}% of revenue: within the 8–10% range", "Polycab investor presentation Q4 FY24, slide 26"),
        29: (f"FY23 capex ₹{inr(capex['FY23'], 0)} cr: above the ₹300–350 cr guided", "Polycab investor presentation Q4 FY24, slide 26"),
        32: (f"Revenue ₹{inr(a.revenue['FY25'], 0)} cr in FY25: target met a year early", f"{AR26}, p.318"),
        33: ("Below 10% in every year: " + ", ".join(f"{v:g}% ({fy})" for fy, v in ex.items()),
             "Polycab investor presentations Q4 FY24–Q4 FY26"),
        35: ("Within or above the range FY23–FY26 (" + ", ".join(f"{m[fy]:.1f}%" for fy in ["FY23", "FY24", "FY25", "FY26"])
             + f"); below in FY22 ({m['FY22']:.1f}%)", ar),
        15: (f"FY26 W&C PBIT margin {sm('Wires and Cables'):.1f}%: above the range", f"{AR26}, p.389"),
        23: (f"FY26 EPC PBIT margin {sm('EPC'):.1f}%: high single digit", f"{AR26}, p.389"),
    }


def _guidance():
    g = load("guidance")
    st.subheader(":material/flag: Management guidance tracker")
    st.caption("Guidance items are management statements from earnings calls (not verified against transcripts). "
               "The dashboard assessment uses only figures verified in the annual reports or presentations; items "
               "those figures cannot test are marked 'Not assessed'.")
    acc = _assessments()
    g = g.assign(assessment=[acc.get(i, ("Not assessed", ""))[0] for i in g.item_no],
                 basis=[acc.get(i, ("", ""))[1] for i in g.item_no])
    only = st.checkbox("Show only assessed items", value=False)
    gg = g[g.assessment != "Not assessed"] if only else g
    table(pd.DataFrame({
        "#": gg.item_no, "Guidance": gg.guidance, "Guided at": gg.guided_at_call, "Target": gg.target,
        "Dashboard assessment": gg.assessment, "Basis (source)": gg.basis}), hide_index=True, width="stretch")
    source(f"Guidance: {XLSX} (earnings-call statements). Assessment: dashboard calculation from the cited documents. "
           f"{len(acc)} of {len(g)} items assessed.")


def render():
    LANE_COLOR.update(zip(LANE_ORDER, SERIES))
    e = _frame()
    with filter_bar("exp"):
        y0, y1 = st.slider("Timeline years", 1980, 2027, (2018, 2027))
    st.subheader(":material/rocket_launch: Expansions, capex and corporate actions")
    fig, n = _timeline(e, y0, y1)
    show(fig)
    undated = int(e.when.isna().sum())
    source(f"Verified entries cite the annual report or presentation (hover); others: {XLSX}. {n} dated entries "
           f"shown, {int(e.verified.sum())} of {len(e)} verified. Quarters and fiscal years are placed mid-period "
           f"(FY = Apr–Mar); {undated} entries have no date and are in the table only.")

    lanes = st.multiselect("Type", LANE_ORDER, default=[], placeholder="All types")
    ee = e[e.lane.isin(lanes)] if lanes else e
    ee = ee.sort_values("when", na_position="last")
    table(pd.DataFrame({
        "Date": ee.date.replace("", "not given"), "Type": ee.category, "Event": ee.event, "Amount": ee.amount,
        "Amount detail": ee.amount_text.fillna(""), "Location": ee.location.fillna(""), "Status": ee.status,
        "Note": ee.note.fillna(""), "Verified": ["✓" if v else "" for v in ee.verified], "Source": ee.src}),
        hide_index=True, width="stretch")

    c1, c2 = st.columns([3, 2])
    with c1:
        fig, d, co = _capex()
        show(fig)
        source(src("cash_flow", ["capex_fixed_assets_purchased"], list(d.period),
                   "Capex spends: " + "; ".join(dict.fromkeys(co.src_label))))
    with c2:
        st.markdown("**Capex: cash flow vs company metric**")
        t = d.assign(diff=d.company - d.cf)
        table(pd.DataFrame({"Year": t.period, "Cash flow": [inr(v) for v in t.cf],
                                   "Company 'capex spends'": [inr(v) for v in t.company],
                                   "Difference": [inr(v) for v in t["diff"]]}), hide_index=True, width="stretch")
        k = load("kpis")
        q = k[(k.kpi == "Capex") & k.period.str.startswith("Q") & k.verified]
        st.caption("The two measures use different definitions. Quarterly capex spends: "
                   + ", ".join(f"{r.period} ₹{inr(r.value, 1)} cr" for r in q.itertuples()) + ". CWIP FY26 ₹1,139 cr.")
        source("Quarterly capex spends: Polycab investor presentation Q2 FY27, slide 16. CWIP: Polycab Annual Report "
               "FY26, p.317.", "Capex note")
    st.divider()
    _guidance()
