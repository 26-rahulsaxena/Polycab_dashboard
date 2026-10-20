"""Financials tab sections in the stock-page style: profit waterfall, debt and coverage, financial position, dividends."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui import (SERIES, THEME, TTM, XLSX, arrow, base_layout, bars, card, cr, inr, kv, kv_card, load, ok_periods,
                q_label, rgba, section, show, source, sparkline, src, wrap_label)

STEPS = [  # (label, column(s), sign, measure)
    ("Revenue", ["revenue"], 1, "absolute"),
    ("Materials & mfg", ["material_cost", "manufacturing_cost"], -1, "relative"),
    ("Gross profit", None, 1, "total"),
    ("Staff & other costs", ["employee_cost", "other_expenses"], -1, "relative"),
    ("EBITDA", None, 1, "total"),
    ("Other income", ["other_income"], 1, "relative"),
    ("Depreciation", ["depreciation"], -1, "relative"),
    ("Finance cost", ["interest"], -1, "relative"),
    ("Exceptional items", ["exceptional_items"], 1, "relative"),
    ("Tax", ["tax"], -1, "relative"),
    ("Net income", None, 1, "total"),
]


SEG_STATED = {  # Sep'26 segment growth the Q2 FY27 presentation states without the amount (verified_overrides)
    "Wires and Cables": (47.0, "Polycab investor presentation Q2 FY27, slide 6"),
    "EPC": (53.0, "Polycab investor presentation Q2 FY27, slide 10"),
}


def _chg(a, b):
    return None if a is None or b is None or pd.isna(a) or pd.isna(b) or not b else (a / b - 1) * 100


def _word(v, pos="up", neg="down"):
    return pos if v >= 0 else neg


def latest_quarter():
    """Latest quarter vs the same quarter a year earlier (YoY) and the previous quarter (QoQ), with generated notes."""
    q = load("quarterly").set_index("period")
    per = list(q.index)
    cur, prev = per[-1], per[-2]
    mon, yy = cur.split("'")
    yago = f"{mon}'{int(yy) - 1:02d}"
    if yago not in q.index:
        return
    c, p, y = q.loc[cur], q.loc[prev], q.loc[yago]
    m = lambda r, col: r[col] / r.revenue * 100
    section(f"Latest quarter: {q_label(cur)} ({cur})", f"Compared with {q_label(yago)} (YoY) and {q_label(prev)} (QoQ)")

    g_rev, g_op, g_pat = _chg(c.revenue, y.revenue), _chg(c.operating_profit, y.operating_profit), _chg(c.pat, y.pat)
    opm_c, opm_y, npm_c = m(c, "operating_profit"), m(y, "operating_profit"), m(c, "pat")

    seg = load("segments_q")
    sv = lambda s, met, pr: seg[(seg.segment == s) & (seg.metric == met) & (seg.period == pr)].value.dropna()
    seg_rows, best = [], None
    for s in ("Wires and Cables", "FMEG", "EPC"):
        r1, r0 = sv(s, "revenue_cr", cur), sv(s, "revenue_cr", yago)
        g = _chg(r1.iloc[0], r0.iloc[0]) if len(r1) and len(r0) else None
        stated = g is None and s in SEG_STATED
        if stated:
            g = SEG_STATED[s][0]
        m1, m0 = sv(s, "pbit_margin_pct", cur), sv(s, "pbit_margin_pct", yago)
        seg_rows.append((s, inr(r1.iloc[0], 0) if len(r1) else "n/a", g, stated,
                         m1.iloc[0] if len(m1) else None, m0.iloc[0] if len(m0) else None))
        if g is not None and (best is None or g > best[1]):
            best = (s, g, m1.iloc[0] if len(m1) else None, m0.iloc[0] if len(m0) else None)

    notes = [
        f"Revenue of ₹{inr(c.revenue, 0)} cr, {_word(g_rev)} {abs(g_rev):.1f}% year on year and "
        f"{_word(_chg(c.revenue, p.revenue))} {abs(_chg(c.revenue, p.revenue)):.1f}% on the previous quarter.",
        f"EBITDA of ₹{inr(c.operating_profit, 0)} cr ({_word(g_op)} {abs(g_op):.1f}% YoY); the EBITDA margin "
        f"{_word(opm_c - opm_y, 'widened', 'narrowed')} to {opm_c:.1f}% from {opm_y:.1f}% "
        f"({arrow(opm_c - opm_y, 1, ' pp')}).",
        f"Net profit of ₹{inr(c.pat, 0)} cr, {_word(g_pat)} {abs(g_pat):.1f}% YoY (net margin {npm_c:.1f}%); "
        f"EPS ₹{inr(c.eps)}.",
    ]
    if best:
        s, g, m1, m0 = best
        notes.append(f"{s} grew fastest ({arrow(g, 1)} YoY)"
                     + (f", with a PBIT margin of {m1:.1f}% against {m0:.1f}% a year earlier." if m1 is not None
                        and m0 is not None else "."))

    c1, c2 = st.columns([1, 1.25], gap="medium")
    with c1, card("lq-notes"):
        st.html(f'<ul class="pc pc-notes">{"".join(f"<li>{n}</li>" for n in notes)}</ul>')
        st.caption("Notes are generated from the figures; they are descriptions, not forecasts or advice.")
        last8 = q.tail(8).reset_index()
        fig = bars(last8, "period", ["revenue", "pat"], ["Revenue", "Net profit"], [SERIES[0], SERIES[2]],
                   title=f"Last {len(last8)} quarters")
        fig.update_layout(height=270)
        show(fig, key="lq_bars")
        source(src("quarterly", ["revenue", "pat"], list(last8.period)), "Last 8 quarters")
    with c2, card("lq-table"):
        def row(lab, f, a, b, cc, pp=False):
            ch = lambda x, z: arrow(x - z, 1, " pp") if pp else arrow(_chg(x, z), 1)
            return (f"<tr><td>{lab}</td><td>{f(a)}</td><td>{f(b)}</td><td>{ch(a, b)}</td><td>{f(cc)}</td>"
                    f"<td>{ch(a, cc)}</td></tr>")
        rs = lambda v: f"₹{inr(v, 0)}"
        body = "".join([
            row("Revenue", rs, c.revenue, y.revenue, p.revenue), row("EBITDA", rs, c.operating_profit,
                                                                     y.operating_profit, p.operating_profit),
            row("Net profit", rs, c.pat, y.pat, p.pat), row("EPS (₹)", lambda v: inr(v), c.eps, y.eps, p.eps),
            row("EBITDA margin", lambda v: f"{v:.1f}%", opm_c, opm_y, m(p, "operating_profit"), pp=True),
            row("Net margin", lambda v: f"{v:.1f}%", npm_c, m(y, "pat"), m(p, "pat"), pp=True)])
        st.html(f'<table class="pc pc-mini"><thead><tr><th>₹ crore</th><th>{cur}</th><th>{yago}</th><th>YoY</th>'
                f'<th>{prev}</th><th>QoQ</th></tr></thead><tbody>{body}</tbody></table>')
        sb = "".join(f"<tr><td>{s}</td><td>{r}</td><td>{arrow(g, 1) if g is not None else 'n/a'}{'*' if st_ else ''}"
                     f"</td><td>{'n/a' if m1 is None else f'{m1:.1f}%'}</td>"
                     f"<td>{'n/a' if m1 is None or m0 is None else arrow(m1 - m0, 1, ' pp')}</td></tr>"
                     for s, r, g, st_, m1, m0 in seg_rows)
        st.html(f'<table class="pc pc-mini pc-mini-gap"><thead><tr><th>Segment</th><th>Revenue {cur}</th><th>YoY</th>'
                f'<th>PBIT margin</th><th>vs {yago}</th></tr></thead><tbody>{sb}</tbody></table>')
        if any(r[3] for r in seg_rows):
            st.caption("* Growth as stated in the Q2 FY27 presentation, which does not give the amount.")
        source(src("quarterly", ["revenue", "operating_profit", "pat"], [cur, yago, prev],
                   "Margins = EBITDA or PAT / revenue. Segments: "
                   + src("segments_q", ["FMEG|revenue_cr"], [cur, yago])
                   + "; " + "; ".join(f"{s} growth: {v[1]}" for s, v in SEG_STATED.items())),
               f"Latest quarter, {cur}")


def waterfall(years):
    """Revenue to net income for one year. Only years with every cost line present are offered."""
    a = load("annual").set_index("period")
    need = ["revenue", "material_cost", "manufacturing_cost", "employee_cost", "other_expenses", "other_income",
            "depreciation", "interest", "tax", "pat"]
    ok = [y for y in years if y in a.index and a.loc[y, need].notna().all()]
    if not ok:
        st.info("No year in the selected range has the full set of P&L lines.")
        return
    y = st.selectbox("Year", ok[::-1], key="wf_year")
    r = a.loc[y]
    labels, measures, values, text = [], [], [], []
    for lab, cols, sign, meas in STEPS:
        if cols is None:
            v = {"Gross profit": r.revenue - r.material_cost - r.manufacturing_cost, "EBITDA": r.operating_profit,
                 "Net income": r.pat}[lab]
        else:
            v = sign * sum(float(r.get(c, 0) or 0) for c in cols)
            if lab == "Exceptional items" and abs(v) < 0.005:
                continue
        labels.append(wrap_label(lab, 12))
        measures.append(meas)
        values.append(0 if meas == "total" else v)
        text.append(f"₹{inr(v, 0)}" if meas in ("absolute", "total") else arrow(v, 0, "", "₹"))
    fig = go.Figure(go.Waterfall(
        x=labels, y=values, measure=measures, text=text, textposition="outside",
        textfont=dict(color=THEME["text"], size=11),
        increasing=dict(marker=dict(color=THEME["up"])), decreasing=dict(marker=dict(color=THEME["down"])),
        totals=dict(marker=dict(color=SERIES[0])), connector=dict(line=dict(color=THEME["grid"], width=1, dash="dot")),
        customdata=text, hovertemplate="%{x}: %{customdata}<extra></extra>"))
    fig = base_layout(fig, None, "₹ crore", height=400)
    fig.update_layout(showlegend=False, hovermode="closest")
    show(fig)
    total_check = r.pat - (r.operating_profit + r.other_income - r.depreciation - r.interest
                           + (r.get("exceptional_items") or 0) - r.tax)
    source(src("annual", ["revenue", "operating_profit", "pat"], [y],
               f"Cost lines, other income, depreciation, finance cost and tax: {XLSX}. The steps add up to net income "
               f"(difference ₹{inr(abs(total_check), 2)} cr)"))
    return y


def profit_flow(y):
    """Sankey: where each rupee of revenue goes in year y (costs out, other income in, down to net income)."""
    r = load("annual").set_index("period").loc[y]
    f = lambda c: float(r.get(c) or 0)
    rev, ebitda, oi = f("revenue"), f("operating_profit"), f("other_income")
    mat = f("material_cost") + f("manufacturing_cost")
    staff = rev - mat - ebitda  # staff + other costs, so the flows balance exactly to the reported EBITDA
    dep, fin, tax, exc = f("depreciation"), f("interest"), f("tax"), f("exceptional_items")
    pbt = ebitda + oi - dep - fin + exc
    net = pbt - tax
    names = ["Revenue", "Materials & mfg", "Staff & other costs", "EBITDA", "Other income", "Depreciation",
             "Finance cost", "Profit before tax", "Tax", "Net income"]
    i = {n: k for k, n in enumerate(names)}
    flows = [("Revenue", "Materials & mfg", mat), ("Revenue", "Staff & other costs", staff),
             ("Revenue", "EBITDA", ebitda), ("EBITDA", "Depreciation", dep), ("EBITDA", "Finance cost", fin),
             ("EBITDA", "Profit before tax", ebitda - dep - fin), ("Other income", "Profit before tax", oi),
             ("Profit before tax", "Tax", tax), ("Profit before tax", "Net income", net)]
    if abs(exc) >= 0.005:
        names.append("Exceptional items")
        i["Exceptional items"] = len(names) - 1
        flows.append(("Exceptional items", "Profit before tax", exc) if exc > 0
                     else ("Profit before tax", "Exceptional items", -exc))
    flows = [fl for fl in flows if fl[2] > 0.005]
    cost = {"Materials & mfg", "Staff & other costs", "Depreciation", "Finance cost", "Tax", "Exceptional items"}
    node_col = [THEME["down"] if n in cost else (THEME["up"] if n == "Other income" else SERIES[0]) for n in names]
    if exc > 0:
        node_col[i["Exceptional items"]] = THEME["up"]
    share = lambda v: f"₹{inr(v, 0)} cr · {v / rev * 100:.1f}% of revenue"
    node_val = {n: sum(v for s, t, v in flows if t == n) or sum(v for s, t, v in flows if s == n) for n in names}
    fig = go.Figure(go.Sankey(
        arrangement="snap", valueformat=",.0f",
        node=dict(label=[f"{n}  ₹{inr(node_val[n], 0)}" for n in names], color=node_col, pad=18, thickness=16,
                  line=dict(color=THEME["mark_line"], width=1), customdata=[share(node_val[n]) for n in names],
                  hovertemplate="%{customdata}<extra></extra>"),
        link=dict(source=[i[s] for s, _, _ in flows], target=[i[t] for _, t, _ in flows],
                  value=[v for *_, v in flows], color=[rgba(node_col[i[t]], 0.32) for _, t, _ in flows],
                  customdata=[f"{s} → {t}<br>{share(v)}" for s, t, v in flows],
                  hovertemplate="%{customdata}<extra></extra>")))
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(color=THEME["text"], size=12))
    show(fig, key="profit_flow")
    source(src("annual", ["revenue", "operating_profit", "pat"], [y],
               f"Cost lines, other income, depreciation, finance cost and tax: {XLSX}. Staff & other costs = revenue − "
               f"materials & manufacturing − reported EBITDA, so every flow balances. Net income here "
               f"₹{inr(net, 2)} cr vs reported PAT ₹{inr(r.pat, 2)} cr"), f"Profit flow, {y}")


def debt_coverage(years):
    a_bs = load("balance_sheet").set_index("period")
    c = load("cash_flow").set_index("period")
    inv_ok = ok_periods("balance_sheet", "investments")
    ys = [y for y in years if y in a_bs.index and y != TTM]
    d = pd.DataFrame({
        "period": ys,
        "debt": [a_bs.borrowings[y] for y in ys],
        "fcf": [c.free_cash_flow.get(y) for y in ys],
        "liquid": [a_bs.cash_and_equivalents[y] + (a_bs.investments[y] if y in inv_ok else float("nan")) for y in ys],
    })
    show(bars(d, "period", ["debt", "fcf", "liquid"], ["Debt (borrowings)", "Free cash flow",
                                                       "Cash and current investments"],
              [SERIES[1], SERIES[2], SERIES[0]], title=None))
    source("Free cash flow (CFO − capex + asset sales): "
           + src("cash_flow", ["cash_from_operating", "capex_fixed_assets_purchased"], ys)
           + ". Current investments: " + src("balance_sheet", ["investments"], ys)
           + f". Borrowings and cash: {XLSX}. Cash and investments is n/a where investments are not verified (before FY21).")


def financial_position(years):
    b = load("balance_sheet").set_index("period")
    ys = [y for y in years if y in b.index and b.loc[y, ["current_assets", "current_liabilities", "non_current_assets",
                                                         "non_current_liabilities"]].notna().all()]
    if not ys:
        st.info("No balance sheet in the selected range.")
        return
    y = st.selectbox("As of", ys[::-1], key="fp_year")
    r = b.loc[y]
    d = pd.DataFrame({"term": ["Short term", "Long term"],
                      "assets": [r.current_assets, r.non_current_assets],
                      "liabs": [r.current_liabilities, r.non_current_liabilities]})
    show(bars(d, "term", ["assets", "liabs"], ["Assets", "Liabilities"], [SERIES[0], SERIES[1]], title=None))
    source(src("balance_sheet", ["trade_payables", "investments"], [y],
               f"Asset and liability totals: {XLSX}. Short term = current; long term = non-current. Liabilities "
               "exclude equity. Current liabilities include acceptances"))


def dividends(last_close):
    k = load("kpis")
    a = load("annual").set_index("period")
    g = lambda name, p: k[(k.kpi == name) & (k.period == p) & k.verified].value
    dps, payout = g("Dividend per share", "FY26"), g("Dividend payout ratio", "FY26")
    dps19 = g("Dividend per share", "FY19")
    cells = []
    if len(dps):
        cells += [kv("Dividend per share (FY26)", f"₹{dps.iloc[0]:g}", "final, recommended May 2026"),
                  kv("Dividend yield", f"{dps.iloc[0] / last_close * 100:.2f}%", "FY26 dividend / last close")]
    if len(payout):
        cells.append(kv("Payout ratio (FY26)", f"~{payout.iloc[0]:g}%", "company figure"))
    paid = a.dividends_paid.get("FY26")
    if pd.notna(paid):
        cells.append(kv("Cash dividends paid (FY26)", f"₹{inr(abs(paid), 0)}<small>cr</small>", "cash-flow statement"))
    if cells:
        kv_card("Dividend summary", cells,
                "Polycab Annual Report FY26, p.409 (dividend per share) and p.320 (dividends paid); Polycab investor "
                "presentation Q4 FY26, slide 17 (payout ratio); yield uses the latest yfinance close."
                + (f" Dividend per share was ₹{dps19.iloc[0]:g} in FY19 (Annual Report FY26, p.70)." if len(dps19) else ""))
    ys = [y for y in ["FY21", "FY22", "FY23", "FY24", "FY25", "FY26"] if pd.notna(a.dividends_paid.get(y))]
    d = pd.DataFrame({"period": ys, "paid": [abs(a.dividends_paid[y]) for y in ys]})
    fig = bars(d, "period", ["paid"], ["Cash dividends paid"], [SERIES[2]], title="Dividend history")
    fig.update_layout(showlegend=False)
    show(fig)
    source(src("annual", ["dividends_paid"], ys,
               "Cash paid in each year (mostly the previous year's final dividend). FY21 is a genuine nil. FY19–FY20 "
               "amounts are not stated, so they are not shown"))
