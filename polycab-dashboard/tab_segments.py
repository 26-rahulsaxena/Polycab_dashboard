"""Segments & KPIs tab: segment revenue / PBIT margin and operating KPIs, with verified sources where checked."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui import table
from ui import card, donut
from ui import (SERIES, THEME, TTM, WARN, XLSX, base_layout, bars, cr, inr, lines, load, pct, period_to_date, show,
                source, src, fy_of_quarter)

SEG_ORDER = ["Wires and Cables", "FMEG", "EPC", "Others"]
SEG_COLOR = {}  # filled per run from the current palette, fixed slot per segment


def _wide(seg, metric, order):
    w = seg[seg.metric == metric].pivot_table(index="period", columns="segment", values="value")
    w = w.reindex([p for p in order if p in w.index]).reset_index()
    return w, [s for s in SEG_ORDER if s in w.columns]


def _break_marker(fig, periods):
    """Dashed line where Others (to FY23) is replaced by EPC (from FY24)."""
    if "FY23" in periods and "FY24" in periods:
        # label lives in the caption under the chart, so it can never collide with the legend or the bars
        fig.add_vline(x=periods.index("FY24") - 0.5, line=dict(color=THEME["text2"], width=1, dash="dash"))
    return fig


def _segments(sel, freq, show_ttm):
    st.subheader(":material/donut_large: Segments")
    name = "segments_y" if freq == "Annual" else "segments_q"
    if freq == "Annual":
        seg = load("segments_y")
        order = [p for p in sel if p in set(seg.period)]
        if not order:
            st.info("Segment data starts in FY21. Widen the year range.")
            return
        seg = seg[seg.period.isin(order)]
    else:
        seg = load("segments_q")
        all_q = list(dict.fromkeys(seg.period))
        fy = {q: fy_of_quarter(q) for q in all_q}
        order = [q for q in all_q if fy[q] in sel or (show_ttm and fy[q] > "FY26")]  # FY27 quarters = "latest"
        if not order:
            st.info(f"Quarterly segment data starts at {all_q[0]}. Widen the year range.")
            return
        seg = seg[seg.period.isin(order)]

    rev, rs = _wide(seg, "revenue_cr", order)
    mar, ms = _wide(seg, "pbit_margin_pct", order)
    c1, c2 = st.columns(2)
    with c1:
        pat = None
        if freq == "Quarterly":
            tv = set(seg[seg.to_verify.fillna(False).astype(bool)].period)
            pat = ["/" if p in tv else "" for p in rev.period]
        fig = bars(rev, "period", rs, rs, [SEG_COLOR[s] for s in rs], title="Segment revenue", patterns=pat)
        show(_break_marker(fig, list(rev.period)) if freq == "Annual" else fig)
        source(src(name, [f"{s}|revenue_cr" for s in rs], list(rev.period),
                   "Segment revenue is before inter-segment elimination, so segments do not add up to consolidated "
                   "revenue"))
    with c2:
        fig = lines(mar, "period", ms, ms, [SEG_COLOR[s] for s in ms], title="Segment PBIT margin (%)")
        show(_break_marker(fig, list(mar.period)) if freq == "Annual" else fig)
        source(src(name, [f"{s}|pbit_margin_pct" for s in ms], list(mar.period), "segment PBIT / segment revenue"))
    if freq == "Annual":
        st.caption("Dashed line: 'Others' (FY21–FY23) and 'EPC' (FY24 on) are different segment definitions; the annual "
                   "reports show the change. They are not joined.")
    else:
        if "Sep'26" in list(rev.period):
            st.caption("Sep'26 W&C and EPC revenue: n/a. The Q2 FY27 presentation gives only their growth (47% and 53% "
                       "year on year), not the amounts.")
        if "Others" in rs:
            st.caption(f"{WARN} The dataset also lists 'Others' for Sep'24 and Dec'24 next to EPC. It is shown as "
                       "given and is not comparable with EPC.")

    if freq == "Annual":
        _mix(rev, rs, order, name)

    # segment total vs consolidated revenue
    if freq == "Annual":
        a = load("annual").set_index("period")
        tot = rev.set_index("period")[rs].sum(axis=1)
        t = pd.DataFrame({"Sum of segments": tot, "Consolidated revenue": a.revenue.reindex(tot.index)})
        t["Difference (eliminations and other)"] = t["Sum of segments"] - t["Consolidated revenue"]
        with st.expander("Segment total vs consolidated revenue (₹ crore)"):
            table(t.T.map(inr), width="stretch")
            st.caption("FY26 inter-segment elimination was ₹355.54 cr, leaving total segment income of ₹28,914.71 cr "
                       "(Polycab Annual Report FY26, p.389).")


def _mix(rev, rs, order, name):
    """Revenue streams for one year: by business (gross segment revenue) and by region (verified exports)."""
    with card("seg-mix"):
        st.subheader(":material/pie_chart: Revenue streams")
        per = st.selectbox("Period", order[::-1], key="seg_mix_period")
        row = rev.set_index("period").loc[per]
        segs = [s for s in rs if pd.notna(row.get(s)) and row.get(s) > 0]
        k = load("kpis")
        exp = k[(k.kpi == "Export revenue") & (k.period == per) & k.verified]
        c1, c2 = st.columns(2)
        with c1:
            show(donut(segs, [row[s] for s in segs], [SEG_COLOR[s] for s in segs], title="By business",
                       center=f"₹{inr(sum(row[s] for s in segs), 0)} cr"))
            source(src(name, [f"{s}|revenue_cr" for s in segs], [per],
                       "gross segment revenue, before inter-segment elimination"))
        with c2:
            if len(exp):
                tot = load("annual").set_index("period").revenue[per]
                e = float(exp.value.iloc[0])
                show(donut(["India", "International"], [tot - e, e], [SERIES[0], SERIES[2]], title="By region",
                           center=f"₹{inr(tot, 0)} cr"))
                source(f"Exports: {exp.src_label.iloc[0]}. Revenue: {src('annual', ['revenue'], [per])}. "
                       "India = revenue − exports.")
            else:
                st.info(f"Region split for {per}: n/a. Export revenue is verified only for FY23–FY26.")


REPORT_BIZ = ("Business description (product range, plants, customer types, FMEG super-distributor model, EPC "
              "projects, online listings): earlier research report, Business overview pp.2–3; not checked "
              "against the annual report")


def company_overview(beside=None):
    """Overview tab: what Polycab does and how it earns money (sourced facts only) in one full-width card; below it,
    `beside` (optional callable, e.g. key stats + company info) on the left and the segment mix on the right."""
    SEG_COLOR.update(zip(SEG_ORDER, SERIES))
    seg = load("segments_y")
    fys = sorted({p for p in seg.period if str(p).startswith("FY")})
    k = load("kpis").set_index(["kpi", "period"])

    def kv_(kpi, per):
        r = k.loc[[(kpi, per)]].iloc[0] if (kpi, per) in k.index else None
        return (None, "") if r is None or pd.isna(r.value) else (float(r.value), r.src_label)

    latest = fys[-1]
    rev, rs = _wide(seg, "revenue_cr", fys)
    mar, _ = _wide(seg, "pbit_margin_pct", fys)
    r_l = rev.set_index("period").loc[latest, rs].dropna()
    wc_share = r_l.get("Wires and Cables", float("nan")) / r_l.sum() * 100
    dealers, s_d = kv_("Authorised dealers and distributors", "Jul 2026")
    outlets, s_o = kv_("Retail outlets", "Jul 2026")
    countries, s_c = kv_("Countries served", latest)
    exp_sh, s_e = kv_("Export share of revenue", latest)
    n = lambda v, f: "n/a" if v is None else f(v)
    text = (
        "Polycab India makes wires and cables, sells fast-moving electrical goods (FMEG) and builds power "
        "infrastructure as an EPC contractor. <b>Wires and cables</b>, the core business, span about 10,000 products "
        f"from building wires to 220 kV cables, made in its own Halol and Daman plants; they were {wc_share:.0f}% of "
        f"{latest} gross segment revenue. Buyers range from real-estate developers and refineries to Indian Railways. "
        "<b>FMEG</b> (fans, lights, switches, solar products) is sold to consumers through a super-distributor model, "
        "dedicated dealers and online marketplaces. <b>EPC</b> takes government power-distribution and broadband "
        "projects that use Polycab's own cables. Products reach buyers through "
        f"{n(dealers, lambda v: f'{inr(v, 0)}+')} authorised dealers and distributors and about "
        f"{n(outlets, lambda v: inr(v, 0))} retail outlets. <b>Exports</b> reach {n(countries, lambda v: f'{v:.0f}')} "
        f"countries and were {n(exp_sh, lambda v: f'{v:.1f}%')} of {latest} revenue; the rest is domestic.")
    full = "; ".join(x for x in [
        REPORT_BIZ,
        f"Dealers and distributors, retail outlets: {s_d}" if s_d else "",
        f"Countries served and export share {latest}: {s_c}, {s_e}" if s_c else "",
        src("segments_y", [f"{s}|revenue_cr" for s in rs], [latest],
            "segment shares are of gross segment revenue, before inter-segment elimination")] if x)

    with card("company"):
        st.subheader(":material/domain: Company overview")
        st.html(f'<div class="pc pc-about">{text}</div>')
        source(full, "Company overview")

    c1, c2 = st.columns([1.1, 1], gap="medium")
    if beside:
        with c1:
            beside()
    with c2, card("company-mix"):
        st.subheader(":material/donut_small: Revenue by segment")
        per = st.segmented_control("Year", [latest, fys[-2]], default=latest, key="ov_mix_year",
                                   help="Latest full year, or the year before") or latest
        row = rev.set_index("period").loc[per]
        m = mar.set_index("period").loc[per]
        segs = [s for s in rs if pd.notna(row.get(s)) and row.get(s) > 0]
        tot = sum(row[s] for s in segs)
        show(donut(segs, [row[s] for s in segs], [SEG_COLOR[s] for s in segs], center=f"₹{inr(tot, 0)} cr",
                   height=250), key="ov_mix_donut")
        rows = "".join(f"<tr><td>{s}</td><td>{inr(row[s], 0)}</td><td>{row[s] / tot * 100:.1f}%</td>"
                       f"<td>{pct(m.get(s))}</td></tr>" for s in segs)
        st.html('<table class="pc pc-mini"><thead><tr><th>Segment</th><th>Revenue (₹ cr)</th><th>% of total</th>'
                f'<th>Margin</th></tr></thead><tbody>{rows}</tbody><tfoot><tr><td>Total (gross)</td>'
                f'<td>{inr(tot, 0)}</td><td>100%</td><td></td></tr></tfoot></table>')
        st.caption("Margin = segment PBIT / segment revenue.")
        st.caption("Segment totals are before inter-segment eliminations, so they exceed consolidated revenue.")
        source(src("segments_y", [f"{s}|revenue_cr" for s in segs] + [f"{s}|pbit_margin_pct" for s in segs], [per],
                   "gross segment revenue before inter-segment elimination; margin = segment PBIT / segment revenue"),
               f"Revenue by segment, {per}")


def _range_bars(df, title, unit="%"):
    """Floating bars for low-high ranges; point values drawn as a thin bar of height 0 + marker."""
    fig = go.Figure()
    lo = df.value_low.fillna(df.value)
    hi = df.value_high.fillna(df.value)
    lab = [f"{l:g}–{h:g}{unit}" if l != h else f"{l:g}{unit}" for l, h in zip(lo, hi)]
    fig.add_bar(x=df.label, y=(hi - lo).where(hi > lo, 0.4), base=lo, marker_color=SERIES[0], name="Range",
                customdata=list(zip(lab, df.src)), text=lab, textposition="outside",
                hovertemplate="%{customdata[0]}<br>%{customdata[1]}<extra></extra>")
    fig = base_layout(fig, title, unit, ysuffix=unit)
    fig.update_layout(showlegend=False, hovermode="closest")
    fig.update_yaxes(rangemode="tozero")
    return fig


def _kpi_frame():
    k = load("kpis").copy()
    k["src"] = k.src_label
    k["date"] = k.period.map(period_to_date)
    k["label"] = k.period
    return k.sort_values("date", kind="stable")


def _fmt_val(r):
    if pd.notna(r.value_low) and pd.notna(r.value_high):
        v = f"{inr(r.value_low, 1 if r.value_low % 1 else 0)}–{inr(r.value_high, 1 if r.value_high % 1 else 0)}"
    elif pd.notna(r.value):
        v = inr(r.value, 2 if r.value % 1 else 0)
    else:
        return "n/a"
    return v + {"%": "%", "Rs cr": " cr", "days": " days", "x": "x", "count": ""}.get(r.unit, f" {r.unit}")


def _kpis():
    st.subheader(":material/speed: Operating KPIs")
    st.caption("Ranges are management estimates. Full source details: see Sources & notes at the bottom of the tab.")
    k = _kpi_frame()
    g = lambda name: k[k.kpi == name]

    c1, c2 = st.columns(2)
    with c1:
        ms = g("Domestic organised W&C market share")
        show(_range_bars(ms, "Domestic organised W&C market share (%)"))
        tm = g("Total W&C market share")
        source("; ".join(dict.fromkeys(ms.src)) + ". Management estimate."
               + (f" Total-market share FY26: {_fmt_val(tm.iloc[0])} ({XLSX})." if len(tm) else ""))
    with c2:
        ex = g("Export share of revenue").dropna(subset=["value"])
        ann = ex[ex.period.str.match(r"^FY\d{2}$")]
        fig = lines(ann, "label", ["value"], ["Export share of revenue"], [SERIES[0]], title="Export share of revenue (%)")
        show(fig)
        qtr = ex[~ex.period.isin(ann.period)]
        source("; ".join(dict.fromkeys(ann.src)) + ". Quarters: "
               + ", ".join(f"{r.period} {r.value:g}%" for r in qtr.itertuples())
               + " (" + "; ".join(dict.fromkeys(qtr.src)) + "). Target: above 10% by FY30.")

    c1, c2 = st.columns(2)
    with c1:
        cs = g("Countries served").dropna(subset=["value"])
        fig = bars(cs, "label", ["value"], ["Countries"], [SERIES[0]], title="Countries served",
                   yaxis_title="countries", fmt=lambda v: f"{v:g}")
        fig.update_layout(showlegend=False)
        show(fig)
        source("; ".join(dict.fromkeys(cs.src)))
    with c2:
        ap = g("Advertisement and sales-promotion spend").dropna(subset=["value"])
        ap = ap[ap.period.str.match(r"^FY\d{2}$")]
        fig = bars(ap, "label", ["value"], ["A&P spend"], [SERIES[3]], title="Advertising and sales-promotion spend")
        fig.update_layout(showlegend=False)
        show(fig)
        source("; ".join(dict.fromkeys(ap.src)))
    st.caption("Customer concentration (top 1/5/10 customers): n/a. It is not stated in the annual reports or "
               "presentations supplied.")

    st.markdown("**Capacity, utilisation and footprint**")
    cards = [
        ("W&C capacity (FY26)", "W&C annual capacity (Halol, Daman)"), ("Fan capacity (FY26)", "Fan annual capacity (Halol, Roorkee)"),
        ("Manufacturing facilities", "Manufacturing facilities"), ("Warehouses and depots", "Warehouses and depots"),
        ("Dealers and distributors", "Authorised dealers and distributors"), ("Retail outlets", "Retail outlets"),
        ("Countries served (FY26)", "Countries served"), ("EPC order book (Jul 2026)", "EPC open order book"),
    ]
    cols = st.columns(4) + st.columns(4)
    for box, (label, name) in zip(cols, cards):
        r = g(name).dropna(subset=["value"]).iloc[-1]
        val = _fmt_val(r)
        if any(w in str(r.note) for w in ("plus", "more than", "+")):
            val += "+"
        box.metric(label, ("₹" + val) if r.unit == "Rs cr" else val, help=f"{r.period}. Source: {r.src}")
    card_src = [g(n).dropna(subset=["value"]).iloc[-1].src for _, n in cards]
    source("Footprint cards: " + "; ".join(dict.fromkeys(card_src)) + ".", "Capacity and footprint cards")
    u = g("Capacity utilisation").dropna(subset=["value"])
    st.caption("Capacity utilisation FY26: " + "; ".join(f"{_fmt_val(r)} ({r.note})" for r in u.itertuples())
               + ". Quarterly utilisation: n/a.")
    source("Capacity utilisation: " + "; ".join(dict.fromkeys(u.src)) + ".", "Capacity utilisation")

    st.markdown("**Working capital: company net working-capital days vs dataset cash conversion cycle**")
    nwc = g("Net working capital days (company, closing)")
    ccc = load("ratios_file").set_index("period").cash_conversion_cycle
    nearest = {"FY24": "FY24", "FY25": "FY25", "FY26": "FY26", "Q2 FY27": TTM}
    table(pd.DataFrame({
        "Period": nwc.period, "Company NWC days (closing)": [f"{v:g}" for v in nwc.value],
        "Detail": nwc.note,
        "Dataset CCC (material-cost days)": [f"{ccc.get(nearest[p]):.1f} ({nearest[p]})" if p in nearest else "n/a"
                                             for p in nwc.period]}), hide_index=True, width="stretch")
    st.caption("Both include acceptances in payables; the company uses its own day-count basis.")
    source(f"Company days: {nwc.src.iloc[0]}. Dataset CCC uses the cited trade payables (Annual Reports FY21–FY26).",
           "Working-capital comparison")

    st.markdown("**Verification results**")
    o = load("verified_overrides")
    stat = st.multiselect("Verification status", ["verified", "changed", "not_found"], default=[],
                          placeholder="All statuses")
    oo = o[o.status.isin(stat)] if stat else o
    table(pd.DataFrame({
        "Item": oo.item, "Period": oo.period, "Value": oo.value.fillna("n/a"), "Unit": oo.unit,
        "Previous value": oo.previous_value.fillna(""), "Status": oo.status, "Source": oo.source_label,
        "Note": oo.note.fillna("")}), hide_index=True, width="stretch")
    cnt = o.status.value_counts()
    st.caption(f"{len(o)} items checked: {cnt.get('verified', 0)} verified, {cnt.get('changed', 0)} changed or newly "
               f"filled, {cnt.get('not_found', 0)} not found. Where a value changed, the dashboard uses the report value.")

    with st.expander("All KPIs"):
        cats = sorted(k.category.dropna().unique())
        pick = st.multiselect("Category", cats, default=[], placeholder="All categories")
        kk = k[k.category.isin(pick)] if pick else k
        table(pd.DataFrame({
            "Category": kk.category, "KPI": kk.kpi, "Period": kk.period, "Value": [_fmt_val(r) for r in kk.itertuples()],
            "Note": kk.note.fillna(""), "Verified": ["✓" if v else "" for v in kk.verified], "Source": kk.src}),
            hide_index=True, width="stretch")
        st.caption(f"{len(k)} KPI rows; {int(kk.verified.sum())} shown are verified against a report or presentation.")


def render(sel, freq, show_ttm):
    SEG_COLOR.update(zip(SEG_ORDER, SERIES))
    _segments(sel, freq, show_ttm)
    st.divider()
    _kpis()
