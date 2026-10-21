"""Forecast tab: a driver-based five-year model (P&L, cash flow, simplified balance sheet, ratios) built from the
last actual year with your assumptions on sliders. Defaults come only from the company's own FY history."""
import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui import (SERIES, THEME, XLSX, arrow, bars, base_layout, card, filter_bar, inr, load, pct, rgba, section,
                show, source, sparkline, src, table)

N = 5  # forecast years
SEGS = ["Wires and Cables", "FMEG", "EPC"]
# slider key -> (label, min, max, step, unit); defaults are computed from history in _defaults()
SLIDERS = {
    "g0": ("Revenue growth, first year (%)", 0.0, 40.0, 0.5, "%"),
    "g1": ("Revenue growth, final year (%)", 0.0, 40.0, 0.5, "%"),
    "seg_Wires and Cables": ("Wires and Cables growth (%)", 0.0, 40.0, 0.5, "%"),
    "seg_FMEG": ("FMEG growth (%)", 0.0, 50.0, 0.5, "%"),
    "seg_EPC": ("EPC growth (%)", -20.0, 50.0, 0.5, "%"),
    "mat": ("Materials & manufacturing (% of revenue)", 60.0, 90.0, 0.1, "%"),
    "staff": ("Staff & other costs (% of revenue)", 2.0, 15.0, 0.1, "%"),
    "oi": ("Other income (% of revenue)", 0.0, 3.0, 0.05, "%"),
    "dep": ("Depreciation (% of revenue)", 0.5, 3.0, 0.05, "%"),
    "fin": ("Finance cost (% of revenue)", 0.0, 2.0, 0.05, "%"),
    "tax": ("Tax rate (% of PBT)", 15.0, 35.0, 0.5, "%"),
    "capex": ("Capex (% of revenue)", 1.0, 10.0, 0.1, "%"),
    "rec": ("Receivable days (on revenue)", 10.0, 90.0, 1.0, "days"),
    "inv": ("Inventory days (on materials & mfg)", 30.0, 150.0, 1.0, "days"),
    "pay": ("Payable days (on materials & mfg)", 20.0, 150.0, 1.0, "days"),
    "payout": ("Dividend payout (% of PAT)", 0.0, 60.0, 1.0, "%"),
}
SCENARIO = {  # stated shifts from Base (percentage points)
    "Bear": {"g0": -5, "g1": -5, "seg_Wires and Cables": -5, "seg_FMEG": -5, "seg_EPC": -5, "mat": 1.0, "staff": 0.5},
    "Bull": {"g0": 5, "g1": 5, "seg_Wires and Cables": 5, "seg_FMEG": 5, "seg_EPC": 5, "mat": -1.0, "staff": -0.5},
}


def _hist():
    a = load("annual").set_index("period")
    b = load("balance_sheet").set_index("period")
    c = load("cash_flow").set_index("period")
    fy = [p for p in a.index if str(p).startswith("FY")]
    return a, b, c, fy


@st.cache_data
def _defaults():
    """Base assumptions: 3-year averages (last three FYs) of each driver; growth = 3-year revenue CAGR;
    payout and tax = last FY. Returns (values, notes, base-year numbers)."""
    a, b, c, fy = _hist()
    y3, last = fy[-3:], fy[-1]
    mm = lambda y: a.material_cost[y] + a.manufacturing_cost[y]
    avg = lambda f: float(sum(f(y) for y in y3) / 3)
    seg = load("segments_y")
    sv = lambda s, y: seg[(seg.segment == s) & (seg.metric == "revenue_cr") & (seg.period == y)].value
    d, note = {}, {}
    g = ((a.revenue[last] / a.revenue[fy[-4]]) ** (1 / 3) - 1) * 100
    d["g0"] = d["g1"] = round(g, 1)
    note["g0"] = note["g1"] = f"{fy[-4]}–{last} revenue CAGR"
    for s in SEGS:
        yrs = [y for y in fy[-4:] if len(sv(s, y).dropna())]
        n = len(yrs) - 1
        d[f"seg_{s}"] = round(((float(sv(s, yrs[-1]).iloc[0]) / float(sv(s, yrs[0]).iloc[0])) ** (1 / n) - 1) * 100, 1)
        note[f"seg_{s}"] = f"{yrs[0]}–{yrs[-1]} CAGR"
    d["mat"] = round(avg(lambda y: mm(y) / a.revenue[y] * 100), 1)
    # staff & other = 1 − materials − reported EBITDA margin, so the default EBITDA margin equals the reported average
    d["staff"] = round(100 - d["mat"] - avg(lambda y: a.operating_profit[y] / a.revenue[y] * 100), 1)
    d["oi"] = round(avg(lambda y: a.other_income[y] / a.revenue[y] * 100), 2)
    d["dep"] = round(avg(lambda y: a.depreciation[y] / a.revenue[y] * 100), 2)
    d["fin"] = round(avg(lambda y: a.interest[y] / a.revenue[y] * 100), 2)
    d["tax"] = round(a.tax[last] / a.pbt[last] * 100, 1)
    d["capex"] = round(avg(lambda y: abs(c.capex_fixed_assets_purchased[y]) / a.revenue[y] * 100), 1)
    d["rec"] = round(avg(lambda y: b.trade_receivables[y] / a.revenue[y] * 365))
    d["inv"] = round(avg(lambda y: b.inventories[y] / mm(y) * 365))
    d["pay"] = round(avg(lambda y: b.trade_payables[y] / mm(y) * 365))
    d["payout"] = round(-a.dividends_paid[last] / a.pat[last] * 100)
    for k in ("mat", "staff", "oi", "dep", "fin", "capex", "rec", "inv", "pay"):
        note[k] = f"average {y3[0]}–{y3[-1]}"
    note["tax"] = note["payout"] = last
    d = {k: float(x) for k, x in d.items()}  # plain floats for the sliders
    base = dict(year=last, revenue=float(a.revenue[last]), rec=float(b.trade_receivables[last]),
                inv=float(b.inventories[last]), pay=float(b.trade_payables[last]),
                fixed=float(b.net_block[last] + b.cwip[last]),
                cash=float(b.cash_and_equivalents[last] + b.investments[last]), debt=float(b.borrowings[last]),
                equity=float(b.equity_capital[last] + b.reserves[last]),
                seg={s: float(sv(s, last).iloc[0]) for s in SEGS if len(sv(s, last).dropna())})
    return d, note, base


def model(base, v, by_segment=False, n=N):
    """Project n years from the base year. v = driver values (percent / days). Returns one row per forecast year."""
    shares = float(dict(zip(load("meta").key, load("meta").value))["Equity Shares (Cr)"])
    rev, seg = base["revenue"], dict(base["seg"])
    nwc = base["rec"] + base["inv"] - base["pay"]
    fixed, cash, equity, debt = base["fixed"], base["cash"], base["equity"], base["debt"]
    other = equity + debt - fixed - nwc - cash  # everything else on the balance sheet, held at the base-year level
    y0 = int(base["year"][2:])
    rows = []
    for t in range(1, n + 1):
        if by_segment and seg:
            new = {s: x * (1 + v[f"seg_{s}"] / 100) for s, x in seg.items()}
            g = (sum(new.values()) / sum(seg.values()) - 1) * 100  # segment mix drives consolidated growth
            seg = new
        else:
            g = v["g0"] + (v["g1"] - v["g0"]) * (t - 1) / max(n - 1, 1)  # straight-line fade
        rev *= 1 + g / 100
        mm = rev * v["mat"] / 100
        staff = rev * v["staff"] / 100
        ebitda = rev - mm - staff
        dep, oi, fin = rev * v["dep"] / 100, rev * v["oi"] / 100, rev * v["fin"] / 100
        pbt = ebitda - dep - fin + oi
        tax = pbt * v["tax"] / 100
        pat = pbt - tax
        nwc_new = rev * v["rec"] / 365 + mm * v["inv"] / 365 - mm * v["pay"] / 365
        d_nwc = nwc_new - nwc
        cfo = pat + dep - d_nwc
        capex = rev * v["capex"] / 100
        fcf = cfo - capex
        div = pat * v["payout"] / 100
        fixed += capex - dep
        cash += fcf - div
        equity += pat - div
        nwc = nwc_new
        rows.append(dict(period=f"FY{y0 + t:02d}E", growth=g, revenue=rev, materials=mm, staff=staff, ebitda=ebitda,
                         dep=dep, oi=oi, fin=fin, pbt=pbt, tax=tax, pat=pat, eps=pat / shares, d_nwc=d_nwc, cfo=cfo,
                         capex=capex, fcf=fcf, div=div, fixed=fixed, nwc=nwc, cash=cash, debt=debt, other=other,
                         equity=equity, net_cash=cash - debt,
                         opm=ebitda / rev * 100, npm=pat / rev * 100, roe=pat / equity * 100,
                         roce=(pbt + fin) / (equity + debt) * 100))
    return pd.DataFrame(rows)


def checks(f):
    """Accounting identities the model must satisfy every year (all within ₹0.01 cr)."""
    tol = 0.01
    prev_cash = f.cash.shift(1)
    return {
        "PAT = EBITDA − depreciation − finance cost + other income − tax":
            ((f.pat - (f.ebitda - f.dep - f.fin + f.oi - f.tax)).abs() < tol).all(),
        "Cash roll-forward: change in cash = FCF − dividends":
            ((f.cash - prev_cash - (f.fcf - f["div"])).iloc[1:].abs() < tol).all(),
        "Balance sheet balances: assets = equity + borrowings":
            ((f.fixed + f.nwc + f.cash + f.other - f.equity - f.debt).abs() < tol).all(),
    }


def _actuals(years):
    """Actual rows in the model's layout (for charts and tables)."""
    a, b, c, _ = _hist()
    out = []
    for y in years:
        mm = a.material_cost[y] + a.manufacturing_cost[y]
        eq = b.equity_capital[y] + b.reserves[y]
        cash = b.cash_and_equivalents[y] + b.investments[y]
        capex = abs(c.capex_fixed_assets_purchased[y]) if y in c.index else float("nan")
        out.append(dict(period=y, revenue=a.revenue[y], materials=mm, staff=a.revenue[y] - mm - a.operating_profit[y],
                        ebitda=a.operating_profit[y], dep=a.depreciation[y], oi=a.other_income[y], fin=a.interest[y],
                        pbt=a.pbt[y], tax=a.tax[y], pat=a.pat[y], eps=a.eps[y],
                        cfo=c.cash_from_operating.get(y), capex=capex, fcf=c.free_cash_flow.get(y),
                        d_nwc=-c.working_capital_changes[y] if y in c.index else float("nan"),  # + = cash tied up
                        div=-a.dividends_paid[y] if pd.notna(a.dividends_paid[y]) else float("nan"),
                        fixed=b.net_block[y] + b.cwip[y],
                        nwc=b.trade_receivables[y] + b.inventories[y] - b.trade_payables[y], cash=cash,
                        debt=b.borrowings[y], equity=eq, net_cash=cash - b.borrowings[y],
                        opm=a.operating_profit[y] / a.revenue[y] * 100, npm=a.pat[y] / a.revenue[y] * 100,
                        roe=a.pat[y] / eq * 100, roce=(a.pbt[y] + a.interest[y]) / (eq + b.borrowings[y]) * 100))
    return pd.DataFrame(out)


# ---------------------------------------------------------------- assumptions UI
def _apply(name):
    d, _, _ = _defaults()
    for k in SLIDERS:
        lo, hi = SLIDERS[k][1], SLIDERS[k][2]
        st.session_state[f"fc_{k}"] = min(hi, max(lo, d[k] + SCENARIO.get(name, {}).get(k, 0)))
    st.session_state["fc_scenario"] = name


def _slider(k, note):
    lab, lo, hi, step, unit = SLIDERS[k]
    fmt = "%.0f days" if unit == "days" else ("%.2f%%" if step < 0.1 else "%.1f%%")
    return st.slider(lab, lo, hi, step=step, format=fmt, key=f"fc_{k}", help=f"Default: {note}")


def _assumptions():
    d, note, base = _defaults()
    for k in SLIDERS:
        st.session_state.setdefault(f"fc_{k}", min(SLIDERS[k][2], max(SLIDERS[k][1], d[k])))
    st.session_state.setdefault("fc_scenario", "Base")
    with filter_bar("fc", "Forecast assumptions"):
        b = st.columns([1, 1, 1, 2, 3.4], vertical_alignment="center")
        b[0].button("Bear", key="fc_bear", on_click=_apply, args=("Bear",), width="stretch",
                    help="Base with growth −5 pp, materials +1 pp, staff & other +0.5 pp")
        b[1].button("Base", key="fc_base", on_click=_apply, args=("Base",), width="stretch",
                    help="Historical defaults (also resets every slider)")
        b[2].button("Bull", key="fc_bull", on_click=_apply, args=("Bull",), width="stretch",
                    help="Base with growth +5 pp, materials −1 pp, staff & other −0.5 pp")
        by_seg = b[3].toggle("Grow by segment", key="fc_byseg",
                             help="Separate growth for W&C, FMEG and EPC; their mix sets consolidated growth")
        b[4].html(f'<div class="pc pc-fc-note">Started from: <b>{st.session_state["fc_scenario"]}</b>. Each slider\'s '
                  f'default comes from {base["year"]} history (hover the ⓘ next to a slider).</div>')
        c = st.columns(4, gap="large")
        with c[0]:
            st.html('<div class="pc pc-fc-group">Growth</div>')
            if by_seg:
                for s in SEGS:
                    if s in base["seg"]:
                        _slider(f"seg_{s}", note[f"seg_{s}"])
            else:
                _slider("g0", note["g0"])
                _slider("g1", note["g1"] + "; lower it to let growth fade")
        with c[1]:
            st.html('<div class="pc pc-fc-group">Operating costs</div>')
            _slider("mat", note["mat"])
            _slider("staff", note["staff"])
            v = {k: st.session_state[f"fc_{k}"] for k in SLIDERS}
            st.html(f'<div class="pc pc-fc-note">Implied EBITDA margin: <b>{100 - v["mat"] - v["staff"]:.1f}%</b></div>')
        with c[2]:
            st.html('<div class="pc pc-fc-group">Below EBITDA</div>')
            for k in ("oi", "dep", "fin", "tax"):
                _slider(k, note[k])
        with c[3]:
            st.html('<div class="pc pc-fc-group">Cash and payout</div>')
            for k in ("capex", "rec", "inv", "pay", "payout"):
                _slider(k, note[k])
    return {k: st.session_state[f"fc_{k}"] for k in SLIDERS}, by_seg, base


# ---------------------------------------------------------------- charts
def _shade(fig, n_act, n_all):
    fig.add_vrect(x0=n_act - 0.5, x1=n_all - 0.5, fillcolor=rgba(THEME["text2"], 0.07), line_width=0, layer="below")
    fig.add_annotation(x=n_act - 0.5, y=1, yref="paper", xanchor="left", yanchor="top", xshift=4, yshift=-2,
                       showarrow=False, text="Forecast →", font=dict(size=11, color=THEME["text2"]))  # inside the band
    return fig


def _bars(d, n_act, cols, names, colors, title):
    pat = ["" if i < n_act else "/" for i in range(len(d))]
    return _shade(bars(d, "period", cols, names, colors, title=title, patterns=pat), n_act, len(d))


def _lines(act, fc, cols, names, colors, title, fmt=pct, ysuffix="%", ytitle="%"):
    """Actual (solid) and forecast (dashed, open markers) parts of each series, joined at the last actual year."""
    fig = go.Figure()
    for col, name, color in zip(cols, names, colors):
        fig.add_scatter(x=act.period, y=act[col], name=name, mode="lines+markers", legendgroup=col,
                        line=dict(color=color, width=2), marker=dict(size=7),
                        customdata=[fmt(x) for x in act[col]], hovertemplate=f"{name}: %{{customdata}}<extra></extra>")
        fig.add_scatter(x=[act.period.iloc[-1], fc.period.iloc[0]], y=[act[col].iloc[-1], fc[col].iloc[0]],
                        mode="lines", line=dict(color=color, width=2, dash="dash"), showlegend=False,
                        hoverinfo="skip", legendgroup=col)
        fig.add_scatter(x=fc.period, y=fc[col], name=f"{name} (forecast)", mode="lines+markers", legendgroup=col,
                        showlegend=False, line=dict(color=color, width=2, dash="dash"),
                        marker=dict(size=7, symbol="circle-open", line=dict(width=2)),
                        customdata=[fmt(x) for x in fc[col]],
                        hovertemplate=f"{name} (forecast): %{{customdata}}<extra></extra>")
    fig = base_layout(fig, title, ytitle, ysuffix=ysuffix)
    fig.update_xaxes(categoryorder="array", categoryarray=list(act.period) + list(fc.period))
    return _shade(fig, len(act), len(act) + len(fc))


def _sensitivity(base, v, by_seg):
    """FY-final PAT change for a +1 pp move in each driver (others fixed)."""
    pat0 = model(base, v, by_seg).pat.iloc[-1]
    drivers = [("Revenue growth", ["g0", "g1"] + [f"seg_{s}" for s in SEGS]), ("Materials & mfg", ["mat"]),
               ("Staff & other", ["staff"]), ("Other income", ["oi"]), ("Depreciation", ["dep"]),
               ("Finance cost", ["fin"]), ("Tax rate", ["tax"])]
    out = []
    for name, keys in drivers:
        w = dict(v)
        for k in keys:
            w[k] = w[k] + 1
        out.append((name, model(base, w, by_seg).pat.iloc[-1] - pat0))
    out.sort(key=lambda x: abs(x[1]))
    fig = go.Figure(go.Bar(
        x=[x for _, x in out], y=[n for n, _ in out], orientation="h",
        marker_color=[THEME["up"] if x >= 0 else THEME["down"] for _, x in out],
        text=[arrow(x, 0, "", "₹") for _, x in out], textposition="outside", cliponaxis=True,
        textfont=dict(size=11, color=THEME["text"]),
        customdata=[f"{arrow(x, 0, '', '₹')} cr ({x / pat0 * 100:+.1f}% of PAT)" for _, x in out],
        hovertemplate="%{y}: %{customdata}<extra></extra>"))
    fig = base_layout(fig, None, None, height=280)
    lim = max(abs(x) for _, x in out) * 2.3 or 1  # room for the outside labels on both sides
    fig.update_xaxes(type="linear", range=[-lim, lim], title="₹ crore change in final-year PAT",
                     title_font=dict(size=12), zeroline=True, zerolinecolor=THEME["zero"], showgrid=True,
                     gridcolor=THEME["grid"], tickformat=",.0f")
    fig.update_yaxes(type="category", title=None, showgrid=False, ticksuffix="  ")
    fig.update_layout(showlegend=False, hovermode="closest", margin=dict(l=10, r=20))
    return fig


# ---------------------------------------------------------------- tables and download
LINES = {
    "P&L": [("Revenue", "revenue"), ("Growth (%)", "growth"), ("Materials & mfg", "materials"),
            ("Staff & other costs", "staff"), ("EBITDA", "ebitda"), ("Depreciation", "dep"), ("Finance cost", "fin"),
            ("Other income", "oi"), ("Profit before tax", "pbt"), ("Tax", "tax"), ("Net profit (PAT)", "pat"),
            ("EPS (₹)", "eps")],
    "Cash flow": [("Operating cash flow (CFO)", "cfo"), ("Change in working capital", "d_nwc"), ("Capex", "capex"),
                  ("Free cash flow", "fcf"), ("Dividends", "div")],
    "Balance sheet": [("Fixed assets (net block + CWIP)", "fixed"), ("Net working capital", "nwc"),
                      ("Cash + current investments", "cash"), ("Borrowings", "debt"), ("Equity", "equity"),
                      ("Net cash", "net_cash")],
    "Ratios": [("EBITDA margin (%)", "opm"), ("Net margin (%)", "npm"), ("ROE (%)", "roe"), ("ROCE (%)", "roce")],
}
PCT_ROWS = {"growth", "opm", "npm", "roe", "roce"}


def _table(act, fc, which):
    allr = pd.concat([act, fc], ignore_index=True)
    if "growth" not in act or act.growth.isna().all():
        allr.loc[: len(act) - 1, "growth"] = act.revenue.pct_change().values * 100
    rows = {}
    for lab, col in LINES[which]:
        s = allr[col] if col in allr else pd.Series([float("nan")] * len(allr))
        rows[lab] = [("n/a" if pd.isna(x) else (f"{x:.1f}%" if col in PCT_ROWS else inr(x, 2 if col == "eps" else 0)))
                     for x in s]
    return pd.DataFrame(rows, index=list(allr.period)).T


def _excel(act, fc):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for which in LINES:
            _table(act, fc, which).to_excel(w, sheet_name=which[:31].replace("&", "and"))
        pd.DataFrame({"Driver": [SLIDERS[k][0] for k in SLIDERS],
                      "Value": [st.session_state.get(f"fc_{k}") for k in SLIDERS]}).to_excel(
            w, sheet_name="Assumptions", index=False)
    return buf.getvalue()


# ---------------------------------------------------------------- tab
def render(sel):
    v, by_seg, base = _assumptions()
    fc = model(base, v, by_seg)
    a, _, _, fy = _hist()
    years = [y for y in sel if y in fy and y <= base["year"]] or fy[-5:]
    if base["year"] not in years:
        years = years + [base["year"]]
    act = _actuals(years)
    ok = checks(fc)
    last, end = base["year"], fc.period.iloc[-1]
    cagr = lambda x1, x0: ((x1 / x0) ** (1 / N) - 1) * 100 if x0 and x0 > 0 and x1 > 0 else None
    act_last = act.set_index("period").loc[last]

    section("Forecast", f"{fc.period.iloc[0]}–{end} from {last} actuals and the assumptions above")
    tiles = []
    for lab, col, color, dec in [("Revenue", "revenue", SERIES[0], 0), ("EBITDA", "ebitda", SERIES[1], 0),
                                 ("Net profit (PAT)", "pat", SERIES[2], 0), ("EPS", "eps", SERIES[3], 2),
                                 ("Free cash flow", "fcf", SERIES[4], 0)]:
        x1, x0 = fc[col].iloc[-1], act_last[col]
        g = cagr(x1, x0)
        unit = "" if col == "eps" else "<small>cr</small>"
        tiles.append(f'<div class="pc-tile"><div class="lab">{lab}, {end}</div><div class="val">₹{inr(x1, dec)}{unit}'
                     f'</div><div class="row"><span class="dl">{arrow(g, 1) if g is not None else "n/a"} CAGR</span>'
                     f'{sparkline(list(act[col]) + list(fc[col]), color, label=lab)}</div>'
                     f'<div class="ft">vs {last} ₹{inr(x0, dec)}</div></div>')
    st.html(f'<div class="pc pc-tiles pc-tiles-5">{"".join(tiles)}</div>')
    st.html('<div class="pc pc-fc-warn"><span class="pc-ico" aria-hidden="true">info</span>Forecast columns (E) are '
            'arithmetic on your assumptions. They are not a forecast by the company, nor investment advice.</div>')

    allr = pd.concat([act, fc], ignore_index=True)
    n_act = len(act)
    c1, c2 = st.columns([3, 2])
    with c1, card("fc-pl"):
        show(_bars(allr, n_act, ["revenue", "ebitda", "pat"], ["Revenue", "EBITDA", "Net profit"],
                   [SERIES[0], SERIES[1], SERIES[2]], "Revenue, EBITDA and net profit"), key="fc_pl")
        source(src("annual", ["revenue", "operating_profit", "pat"], years,
                   "Hatched bars = forecast from your assumptions"), "Forecast: revenue, EBITDA, PAT")
    with c2, card("fc-margin"):
        show(_lines(act, fc, ["opm", "npm"], ["EBITDA margin", "Net margin"], [SERIES[1], SERIES[2]], "Margins (%)"),
             key="fc_margin")
        source(src("annual", ["revenue", "operating_profit", "pat"], years, "Dashed = forecast"), "Forecast: margins")
    c1, c2 = st.columns([3, 2])
    with c1, card("fc-cash"):
        cash = allr.assign(capex_pos=allr.capex)
        show(_bars(cash, n_act, ["cfo", "capex_pos", "fcf"], ["Operating cash flow", "Capex", "Free cash flow"],
                   [SERIES[0], SERIES[3], SERIES[2]], "CFO, capex and free cash flow"), key="fc_cash")
        source(src("cash_flow", ["cash_from_operating", "capex_fixed_assets_purchased"], years,
                   "Forecast CFO = PAT + depreciation − change in working capital (simplified: other items ignored); "
                   "FCF = CFO − capex"), "Forecast: cash flow")
    with c2, card("fc-netcash"):
        show(_lines(act, fc, ["net_cash", "equity"], ["Net cash", "Equity"], [SERIES[4], SERIES[5]],
                    "Net cash and equity (₹ crore)", fmt=lambda x: f"₹{inr(x, 0)} cr", ysuffix="", ytitle="₹ crore"),
             key="fc_netcash")
        source(src("balance_sheet", ["borrowings", "investments"], years,
                   "Net cash = cash + current investments − borrowings; borrowings held at the base-year level"),
               "Forecast: net cash and equity")

    c1, c2 = st.columns([3, 2])
    with c1, card("fc-tables"):
        st.subheader(":material/table_view: Forecast statements (₹ crore)")
        which = st.segmented_control("Statement", list(LINES), default="P&L", key="fc_table") or "P&L"
        table(_table(act, fc, which), width="stretch")
        d1, d2, _ = st.columns([1, 1, 2.2])
        csv = pd.concat({w: _table(act, fc, w) for w in LINES}).to_csv().encode("utf-8")
        d1.download_button("CSV", csv, "polycab_forecast.csv", "text/csv", key="fc_csv",
                           icon=":material/download:")
        d2.download_button("Excel", _excel(act, fc), "polycab_forecast.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="fc_xlsx",
                           icon=":material/download:")
        source(f"Actual columns: {src('annual', ['revenue', 'operating_profit', 'pat'], years)}; cost lines, "
               f"balance sheet and cash flow: {XLSX}. Staff & other (actual) = revenue − materials & mfg − EBITDA. "
               "Balance sheet is simplified: other assets and liabilities held at the base-year level.",
               "Forecast statements")
    with c2, card("fc-sens"):
        st.subheader(":material/tune: What moves final-year PAT")
        st.caption(f"Change in {end} PAT if each driver rises by 1 percentage point (others unchanged).")
        show(_sensitivity(base, v, by_seg), key="fc_sens")
        source("Dashboard calculation on your assumptions; each driver moved by +1 pp from its slider value.",
               "Forecast sensitivity")
        good = all(ok.values())
        st.html(f'<div class="pc pc-fc-checks"><b>{"✓" if good else "✗"} Model checks {sum(ok.values())}/{len(ok)}'
                f'</b><ul>' + "".join(f'<li>{"✓" if x else "✗"} {k}</li>' for k, x in ok.items()) + "</ul></div>")
        g_imp = cagr(fc.revenue.iloc[-1], act_last.revenue)
        st.button("Use in valuation calculator", key="fc_to_calc", icon=":material/calculate:",
                  on_click=_to_calc, args=(g_imp, fc.npm.iloc[-1]),
                  help="Sets the Ratios-tab calculator to this forecast's revenue CAGR, final-year net margin and "
                       "5 years (the calculator starts from TTM revenue, so results differ slightly).")


def _to_calc(g, m):
    st.session_state["calc_g"] = float(min(35.0, max(0.0, round(g or 0, 1))))
    st.session_state["calc_m"] = float(min(16.0, max(3.0, round(m, 1))))
    st.session_state["calc_n"] = N
